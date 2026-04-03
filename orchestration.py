from __future__ import annotations

from openai import OpenAI

from config.openAPI import OPENAI_API_KEY
from config.dbConnection import collection
from tool.tool import OPENAI_TOOLS, calc, get_time
from tool.vuln_tool import shell_exec, python_eval, write_file, read_file, VULN_OPENAI_TOOLS
from utility.template import calc_template, get_time_template
from utility.prompt_vector import vectorize_query
from hijack import (
    DEFAULT_AGENT_TOOL_POLICY,
    require_user_confirmation_for_risky_tool,
    validate_rw_separation,
    validate_tool_call,
)


def build_system_prompt(role: str) -> str:
    base = (
        "당신은 사용자의 질문에 답변하는 AI 어시스턴트입니다.\n"
        "[공통 도구]\n"
        "- 산술 계산 요청에는 calc를 사용하세요.\n"
        "- 시간 요청에는 get_time을 사용하세요.\n"
    )
    if role == "admin":
        return (
            base
            + "[관리자 전용 도구]\n"
            + "- read_file\n"
            + "- write_file\n"
            + "- shell_exec\n"
            + "- python_eval\n"
            + "- 파일명/경로는 번역하거나 변형하지 말고 사용자 입력 원문 그대로 사용하세요.\n"
        )
    return base + "관리자 전용 도구 요청은 거절하세요.\n"


RAG_SYSTEM_PROMPT = (
    "당신은 제공된 Context만 근거로 답변해야 합니다. "
    "외부 정보에 의존하지 마세요."
)


client = OpenAI(api_key=OPENAI_API_KEY)
RW_POLICY_OK, RW_POLICY_MSG = validate_rw_separation(policy=DEFAULT_AGENT_TOOL_POLICY)
if not RW_POLICY_OK:
    raise ValueError(RW_POLICY_MSG)


COMMON_FUNCS = {
    "calc": calc,
    "get_time": get_time,
}
ADMIN_FUNCS = {
    "shell_exec": shell_exec,
    "python_eval": python_eval,
    "write_file": write_file,
    "read_file": read_file,
}


def build_funcs(role: str) -> dict:
    return {**COMMON_FUNCS, **(ADMIN_FUNCS if role == "admin" else {})}


def build_tools(role: str) -> list:
    return OPENAI_TOOLS + (VULN_OPENAI_TOOLS if role == "admin" else [])


def tool_start(user_input: str, role: str) -> tuple[list, list]:
    messages = [
        {"role": "system", "content": build_system_prompt(role)},
        {"role": "user", "content": user_input},
    ]
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=build_tools(role),
        temperature=0.7,
        top_p=0.7,
    )
    assistant_msg = res.choices[0].message

    if assistant_msg.tool_calls:
        serialized_calls = [
            {"id": t.id, "name": t.function.name, "arguments": t.function.arguments}
            for t in assistant_msg.tool_calls
        ]
        messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "id": t.id,
                        "type": "function",
                        "function": {"name": t.function.name, "arguments": t.function.arguments},
                    }
                    for t in assistant_msg.tool_calls
                ],
            }
        )
    else:
        serialized_calls = []
        messages.append({"role": "assistant", "content": assistant_msg.content or ""})

    return messages, serialized_calls


def tool_execute_one(
    messages: list,
    tool_call: dict,
    role: str,
    user_confirmed_risky: bool = False,
) -> list:
    msgs = list(messages)
    funcs = build_funcs(role)
    name = tool_call["name"]

    is_valid, valid_msg, executor_agent, args = validate_tool_call(
        tool_call=tool_call,
        role=role,
        allowed_tool_names=set(funcs.keys()),
        policy=DEFAULT_AGENT_TOOL_POLICY,
    )

    print(f"[LOG] 도구 호출: {name}, 실행 에이전트: {executor_agent}")

    if not is_valid:
        ans = f"하이재킹 방어로 차단됨: {valid_msg}"
        msgs.append({"tool_call_id": tool_call["id"], "role": "tool", "name": name, "content": ans})
        return msgs

    confirm_ok, confirm_msg = require_user_confirmation_for_risky_tool(
        tool_name=name,
        args=args,
        user_confirmed=user_confirmed_risky,
    )
    if not confirm_ok:
        ans = f"하이재킹 방어로 차단됨: {confirm_msg}"
        msgs.append({"tool_call_id": tool_call["id"], "role": "tool", "name": name, "content": ans})
        return msgs

    func = funcs.get(name)
    if func is None:
        ans = "오류: 알 수 없는 함수입니다."
    else:
        try:
            ans = str(func(**args))
            print(f"[LOG] 도구 실행 결과: {ans[:100]}")
        except Exception as e:
            print(f"[LOG] 도구 실행 오류: {e}")
            ans = f"오류: {e}"

    if name == "calc":
        ans = calc_template(ans, args.get("a"), args.get("b"), args.get("c"))
    elif name == "get_time":
        ans = get_time_template(ans)

    msgs.append({"tool_call_id": tool_call["id"], "role": "tool", "name": name, "content": ans})
    return msgs


def tool_finish(messages: list) -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.7, top_p=0.7
    ).choices[0].message.content


def run_rag(user_input: str, n_results: int = 3) -> str:
    query_vector = vectorize_query(user_input)
    results = collection.query(query_embeddings=[query_vector], n_results=n_results)
    context = "\n---\n".join(results["documents"][0])

    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": f"[Context]\n{context}\n\n[질문]\n{user_input}"},
    ]
    return client.chat.completions.create(model="gpt-4o-mini", messages=messages).choices[0].message.content
