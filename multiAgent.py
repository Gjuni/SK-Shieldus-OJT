from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
import operator
import json

from config.openAPI import OPENAI_API_KEY
from orchestration import run_orchestration, run_rag

llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)

# ── State ─────────────────────────────────────────────────────
class AgentState(TypedDict):
    user_input:   str
    routes:       list[str] # list 형식으로 여러 Agent를 병렬 호출
    answers:      Annotated[list[str], operator.add]  # 병렬 결과 자동 누적
    final_answer: str

# ── Agent Registry ────────────────────────────────────────────
# 새 에이전트 추가 시 여기에만 등록하면 됨 (if/elif 불필요)
AGENT_REGISTRY: dict[str, callable] = {
    "tool": run_orchestration,
    "rag":  run_rag,
}
AVAILABLE_AGENTS = list(AGENT_REGISTRY.keys())

# ── Supervisor: 필요한 에이전트를 리스트로 결정 ───────────────
def supervisor(state: AgentState) -> AgentState:
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
        routes = [r for r in json.loads(content) if r in AGENT_REGISTRY] # r이 Agnet에 존재하면 json으로 변환
    except Exception:
        routes = ["rag"]
    return {"routes": routes or ["rag"]}

# ── Fan-out: Send로 병렬 분기 (if/elif 없음) ─────────────────
def fan_out(state: AgentState):
    return [
        Send(route, {
            "user_input":   state["user_input"],
            "routes":       [],
            "answers":      [],
            "final_answer": ""
        })
        for route in state["routes"]
    ]

# ── 에이전트 노드 팩토리: Registry 기반 동적 생성 ─────────────
def make_agent_node(agent_name: str):
    def node(state: AgentState) -> dict:
        result = AGENT_REGISTRY[agent_name](state["user_input"])
        return {"answers": [f"[{agent_name.upper()} Agent]\n{result}"]}
    node.__name__ = f"{agent_name}_node"
    return node

# ── Aggregator: 병렬 응답 수집 후 최종 답변 합성 ─────────────
def aggregator(state: AgentState) -> AgentState:
    if len(state["answers"]) == 1:
        # 단일 에이전트: 접두사 제거 후 그대로 반환
        final = state["answers"][0].split("\n", 1)[-1]
    else:
        # 복수 에이전트: LLM으로 응답 통합
        combined = "\n\n".join(state["answers"])
        prompt = f"""
            다음은 여러 에이전트가 병렬로 생성한 응답입니다.
            이를 자연스럽게 통합하여 최종 답변을 하나로 작성하세요.

            {combined}
        """
        final = llm.invoke(prompt).content
    return {"final_answer": final}

# ── 그래프 조립 (Registry 기반 자동 등록) ────────────────────
graph = StateGraph(AgentState)

graph.add_node("supervisor", supervisor)
graph.add_node("aggregator", aggregator)

# 에이전트 추가 시 아래 루프가 자동으로 노드·엣지 등록
for name in AGENT_REGISTRY:
    graph.add_node(name, make_agent_node(name)) ## node에 대한 결과를 받아옴
    graph.add_edge(name, "aggregator") ## 최종 응답 반환

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", fan_out)  # Send → 병렬 실행
graph.add_edge("aggregator", END)

app = graph.compile()
