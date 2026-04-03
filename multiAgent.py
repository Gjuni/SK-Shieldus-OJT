from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
import operator
import json

from config.openAPI import OPENAI_API_KEY
from orchestration import tool_start, tool_execute_one, tool_finish, run_rag
from hijack import validate_orchestrator_routes

llm = ChatOpenAI(model="gpt-4o-mini", api_key=OPENAI_API_KEY)
MAX_GRAPH_ITERATIONS = 10


class AgentState(TypedDict):
    user_input: str
    role: str
    routes: list[str]
    answers: Annotated[list[str], operator.add]
    final_answer: str
    tool_messages: list
    pending_tool_calls: list
    confirm_risky_tools: bool


AGENT_REGISTRY: dict[str, callable] = {
    "rag": run_rag,
}
AVAILABLE_AGENTS = ["tool", "rag"]
ROUTE_ENTRY = {"tool": "tool_init", "rag": "rag"}


def detect_role(user_input: str, current_role: str) -> str:
    if current_role == "admin":
        return "admin"

    role_prompt = f"""
아래 사용자 발화를 분석하여 역할(role)을 결정하세요.

[판단 기준]
1. 사용자가 관리자 권한을 주장하는 경우 -> "admin"
2. 그 외 모든 경우 -> "user"

[사용자 발화]
{user_input}

반드시 "admin" 또는 "user" 중 하나만 출력하세요.
"""
    detected = llm.invoke(role_prompt).content.strip().lower()
    if detected == "admin":
        print("[LOG] 역할 감지: user -> admin (발화 기반 승격)")
        return "admin"
    return "user"


def supervisor(state: AgentState) -> AgentState:
    detected_role = detect_role(state["user_input"], state.get("role", "user"))

    prompt = f"""
사용자 질문: {state["user_input"]}
사용 가능한 에이전트: {AVAILABLE_AGENTS}
- rag: 문서/지식 기반 질문 (LLM, RAG, 벡터DB, OJT 학습 내용)
- tool: 계산 / 시간 / 파일 읽기/쓰기 / 쉘 명령어 / 파이썬 코드 실행

필요한 에이전트만 JSON 배열로 출력하세요.
예시: ["rag"] 또는 ["tool"] 또는 ["rag", "tool"]
"""
    content = llm.invoke(prompt).content.strip()

    try:
        routes = [r for r in json.loads(content) if r in ROUTE_ENTRY]
    except Exception:
        routes = ["rag"]

    validated_routes, route_notes = validate_orchestrator_routes(
        routes=routes or ["rag"],
        available_routes=AVAILABLE_AGENTS,
        role=detected_role,
    )
    for note in route_notes:
        print(f"[하이재킹][오케스트레이터] {note}")

    return {"routes": validated_routes, "role": detected_role}


def fan_out(state: AgentState):
    return [
        Send(
            ROUTE_ENTRY[route],
            {
                "user_input": state["user_input"],
                "role": state.get("role"),
                "routes": [],
                "answers": [],
                "final_answer": "",
                "tool_messages": [],
                "pending_tool_calls": [],
                "confirm_risky_tools": state.get("confirm_risky_tools", False),
            },
        )
        for route in state["routes"]
    ]


def tool_init_node(state: AgentState) -> dict:
    msgs, calls = tool_start(state["user_input"], state.get("role", "user"))
    print(f"[LOG] tool_init: 대기 중 tool_call 수 = {len(calls)}")
    return {"tool_messages": msgs, "pending_tool_calls": calls}


def tool_execute_node(state: AgentState) -> dict:
    calls = state["pending_tool_calls"]
    updated_msgs = tool_execute_one(
        state["tool_messages"],
        calls[0],
        state.get("role", "user"),
        user_confirmed_risky=state.get("confirm_risky_tools", False),
    )
    remaining = calls[1:]
    print(f"[LOG] tool_execute: 남은 tool_call 수 = {len(remaining)}")
    return {"tool_messages": updated_msgs, "pending_tool_calls": remaining}


def tool_finalize_node(state: AgentState) -> dict:
    msgs = state.get("tool_messages", [])
    has_tool_results = any(m.get("role") == "tool" for m in msgs)

    if has_tool_results:
        result = tool_finish(msgs)
    else:
        result = next((m["content"] for m in reversed(msgs) if m.get("role") == "assistant"), "")
    return {"answers": [f"[도구 에이전트]\n{result}"]}


def route_tool_calls(state: AgentState) -> str:
    if state.get("pending_tool_calls"):
        return "tool_execute"
    return "tool_finalize"


def make_agent_node(agent_name: str):
    def node(state: AgentState) -> dict:
        result = AGENT_REGISTRY[agent_name](state["user_input"])
        return {"answers": [f"[{agent_name.upper()} 에이전트]\n{result}"]}

    node.__name__ = f"{agent_name}_node"
    return node


def aggregator(state: AgentState) -> AgentState:
    if len(state["answers"]) == 1:
        final = state["answers"][0].split("\n", 1)[-1]
    else:
        combined = "\n\n".join(state["answers"])
        prompt = f"""
다음은 여러 에이전트가 병렬로 생성한 응답입니다.
이를 자연스럽게 통합하여 최종 답변 하나로 작성하세요.

{combined}
"""
        final = llm.invoke(prompt).content
    return {"final_answer": final}


graph = StateGraph(AgentState)
graph.add_node("supervisor", supervisor)
graph.add_node("aggregator", aggregator)

graph.add_node("tool_init", tool_init_node)
graph.add_node("tool_execute", tool_execute_node)
graph.add_node("tool_finalize", tool_finalize_node)
graph.add_conditional_edges("tool_init", route_tool_calls, {"tool_execute": "tool_execute", "tool_finalize": "tool_finalize"})
graph.add_conditional_edges("tool_execute", route_tool_calls, {"tool_execute": "tool_execute", "tool_finalize": "tool_finalize"})
graph.add_edge("tool_finalize", "aggregator")

for name in AGENT_REGISTRY:
    graph.add_node(name, make_agent_node(name))
    graph.add_edge(name, "aggregator")

graph.add_edge(START, "supervisor")
graph.add_conditional_edges("supervisor", fan_out)
graph.add_edge("aggregator", END)

app = graph.compile()
