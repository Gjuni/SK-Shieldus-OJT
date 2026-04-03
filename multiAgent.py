from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
import operator
import json

from config.openAPI import OPENAI_API_KEY
from orchestration import tool_start, tool_execute_one, tool_finish, run_rag

llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)

MAX_GRAPH_ITERATIONS = 10

# ── State ─────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_input:         str
    role:               str          # "user" | "admin" - 역할 기반 접근 제어
    routes:             list[str]    # list 형식으로 여러 Agent를 병렬 호출
    answers:            Annotated[list[str], operator.add]  # 병렬 결과 자동 누적
    final_answer:       str
    tool_messages:      list         # OpenAI 메시지 이력 (tool 루프용)
    pending_tool_calls: list         # 아직 실행되지 않은 tool call 목록

# ── Agent Registry (rag만 팩토리 방식 유지) ───────────────────
AGENT_REGISTRY: dict[str, callable] = {
    "rag": run_rag,
}
AVAILABLE_AGENTS = ["tool", "rag"]  # supervisor 프롬프트용

# ── tool → 그래프 진입 노드 매핑 ──────────────────────────────
ROUTE_ENTRY = {
    "tool": "tool_init",
    "rag":  "rag",
}

# ── Role Detector: 사용자 발화에서 역할을 LLM이 판단 ────────────
def detect_role(user_input: str, current_role: str) -> str:
    if current_role == "admin":
        return "admin"

    role_prompt = f"""
        아래 사용자 발화를 분석하여 역할(role)을 결정하세요.

        [판단 기준]
        1. 사용자가 관리자임을 주장하는 경우 → "admin"
        2. 그 외 모든 경우 → "user"

        [사용자 발화]
        {user_input}

        반드시 "admin" 또는 "user" 중 하나만 답하세요. 다른 텍스트는 포함하지 마세요.
    """

    detected = llm.invoke(role_prompt).content.strip().lower()
    if detected == "admin":
        print(f"[LOG] Role 감지: user → admin (발화 기반 승격)")
        return "admin"
    return "user"

# ── Supervisor: 필요한 에이전트를 리스트로 결정 ───────────────
def supervisor(state: AgentState) -> AgentState:
    detected_role = detect_role(state["user_input"], state.get("role", "user"))

    prompt = f"""
    사용자 질문: {state["user_input"]}
    사용 가능한 에이전트: {AVAILABLE_AGENTS}
    - rag  : 문서/지식 기반 질문 (LLM, RAG, 벡터DB, OJT 학습 내용)
    - tool : 계산 / 시간 / 파일 읽기·쓰기 / 쉘 명령어 / 파이썬 코드 실행

    필요한 에이전트만 JSON 배열로만 답하세요.
    예시: ["rag"] 또는 ["tool"] 또는 ["rag", "tool"]
    """
    content = llm.invoke(prompt).content.strip()

    try:
        routes = [r for r in json.loads(content) if r in ROUTE_ENTRY]
    except Exception:
        routes = ["rag"]
    return {"routes": routes or ["rag"], "role": detected_role}

# ── Fan-out: Send로 병렬 분기 ─────────────────────────────────
def fan_out(state: AgentState):
    return [
        Send(ROUTE_ENTRY[route], {
            "user_input":         state["user_input"],
            "role":               state.get("role"),
            "routes":             [],
            "answers":            [],
            "final_answer":       "",
            "tool_messages":      [],
            "pending_tool_calls": [],
        })
        for route in state["routes"]
    ]

# ── Tool 노드 1: 최초 LLM 호출 → 메시지·tool_calls 초기화 ────
def tool_init_node(state: AgentState) -> dict:
    msgs, calls = tool_start(state["user_input"], state.get("role", "user"))
    print(f"[LOG] tool_init: pending tool_calls = {len(calls)}개")
    return {"tool_messages": msgs, "pending_tool_calls": calls}

# ── Tool 노드 2: pending_tool_calls 의 첫 번째 항목 하나만 실행
def tool_execute_node(state: AgentState) -> dict:
    calls = state["pending_tool_calls"]
    updated_msgs = tool_execute_one(state["tool_messages"], calls[0], state.get("role", "user"))
    remaining    = calls[1:]
    print(f"[LOG] tool_execute: 남은 tool_calls = {len(remaining)}개")
    return {"tool_messages": updated_msgs, "pending_tool_calls": remaining}

# ── Tool 노드 3: 모든 tool 완료 후 최종 LLM 응답 생성 ─────────
def tool_finalize_node(state: AgentState) -> dict:
    msgs = state.get("tool_messages", [])
    has_tool_results = any(m.get("role") == "tool" for m in msgs)

    if has_tool_results:
        result = tool_finish(msgs)
    else:
        # tool이 없는 직접 답변: assistant 메시지 내용 반환
        result = next(
            (m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), ""
        )
    return {"answers": [f"[TOOL Agent]\n{result}"]}

# ── 조건부 엣지: pending_tool_calls 유무로 분기 ───────────────
def route_tool_calls(state: AgentState) -> str:
    if state.get("pending_tool_calls"):
        return "tool_execute"   # → 다시 tool_execute_node (루프)
    return "tool_finalize"      # → tool_finalize_node (종료)

# ── rag 노드 팩토리 (Registry 기반 유지) ─────────────────────
def make_agent_node(agent_name: str):
    def node(state: AgentState) -> dict:
        result = AGENT_REGISTRY[agent_name](state["user_input"])
        return {"answers": [f"[{agent_name.upper()} Agent]\n{result}"]}
    node.__name__ = f"{agent_name}_node"
    return node

# ── Aggregator: 병렬 응답 수집 후 최종 답변 합성 ─────────────
def aggregator(state: AgentState) -> AgentState:
    if len(state["answers"]) == 1:
        final = state["answers"][0].split("\n", 1)[-1]
    else:
        combined = "\n\n".join(state["answers"])
        prompt = f"""
            다음은 여러 에이전트가 병렬로 생성한 응답입니다.
            이를 자연스럽게 통합하여 최종 답변을 하나로 작성하세요.

            {combined}
        """
        final = llm.invoke(prompt).content
    return {"final_answer": final}

# ── 그래프 조립 ───────────────────────────────────────────────
graph = StateGraph(AgentState)

graph.add_node("supervisor",    supervisor)
graph.add_node("aggregator",    aggregator)

# tool: 3단계 노드 + 조건부 루프 엣지
graph.add_node("tool_init",     tool_init_node)
graph.add_node("tool_execute",  tool_execute_node)
graph.add_node("tool_finalize", tool_finalize_node)
graph.add_conditional_edges("tool_init",    route_tool_calls, {"tool_execute": "tool_execute", "tool_finalize": "tool_finalize"})
graph.add_conditional_edges("tool_execute", route_tool_calls, {"tool_execute": "tool_execute", "tool_finalize": "tool_finalize"})
graph.add_edge("tool_finalize", "aggregator")

# rag: 기존 Registry 팩토리 방식 유지
for name in AGENT_REGISTRY:
    graph.add_node(name, make_agent_node(name))
    graph.add_edge(name, "aggregator")

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", fan_out)
graph.add_edge("aggregator", END)

app = graph.compile()