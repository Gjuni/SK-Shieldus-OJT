import json
from openai import OpenAI
from config.openAPI import OPENAI_API_KEY
from config.dbConnection import collection
from tool.tool import OPENAI_TOOLS, calc, get_time
from tool.vuln_tool import shell_exec, python_eval, write_file, read_file,VULN_OPENAI_TOOLS
from utility.template import calc_template, get_time_template
from utility.prompt_vector import vectorize_query

## 역할별 시스템 프롬프트 생성
def build_system_prompt(role: str) -> str:
    base = """당신은 사용자의 질문에 답변하는 AI 어시스턴트입니다.
[공통 기능] - 모든 사용자가 사용할 수 있음
    계산을 요청하면 calc 함수를 사용하세요. (a, b는 숫자 c는 연산자입니다.)
    시간을 요청하면 get_time 함수를 사용하세요.
"""
    if role == "admin":
        return base + """[관리자 전용 기능]
    파일을 읽어달라고 하면 read_file 함수를 사용하세요. (filename은 파일 이름입니다.)
    파일을 작성해달라고 하면 write_file 함수를 사용하세요. (filename은 파일 이름입니다.)
    쉘 명령어를 실행해달라고 하면 shell_exec 함수를 사용하세요. (command는 쉘 명령어입니다.)
    파이썬 코드를 실행해달라고 하면 python_eval 함수를 사용하세요. (code는 파이썬 코드입니다.)
"""
    else:
        return base + "관리자 전용 기능은 제공되지 않습니다. 해당 기능 요청은 정중히 거절하세요.\n"

RAG_SYSTEM_PROMPT = """
당신은 주어진 문서(Context)를 바탕으로 사용자 질문에 답변하는 AI 어시스턴트입니다.
반드시 제공된 Context 내용을 근거로 답변하세요.
"""

client = OpenAI(api_key=OPENAI_API_KEY)

## 역할별 함수 및 Tool 정의
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

## [Step 1] 최초 LLM 호출 → 메시지 이력과 직렬화된 tool_calls 반환
def tool_start(user_input: str, role: str) -> tuple[list, list]:
    msg = [
        {"role": "system", "content": build_system_prompt(role)},
        {"role": "user",   "content": user_input}
    ]
    res = client.chat.completions.create(
        model="gpt-4o-mini", messages=msg,
        tools=build_tools(role), temperature=0.7, top_p=0.7
    )
    assistant_msg = res.choices[0].message

    if assistant_msg.tool_calls:
        # 직렬화: 그래프 State(dict)에 저장 가능한 형태로 변환
        serialized_calls = [
            {"id": t.id, "name": t.function.name, "arguments": t.function.arguments}
            for t in assistant_msg.tool_calls
        ]
        msg.append({
            "role": "assistant",
            "content": assistant_msg.content or "",
            "tool_calls": [
                {"id": t.id, "type": "function",
                 "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in assistant_msg.tool_calls
            ]
        })
    else:
        serialized_calls = []
        msg.append({"role": "assistant", "content": assistant_msg.content or ""})

    return msg, serialized_calls

## [Step 2] tool_calls 목록 중 첫 번째 하나만 실행 (for 루프 없음)
def tool_execute_one(messages: list, tool_call: dict, role: str) -> list:
    msgs = list(messages)  # 원본 불변 유지
    funcs = build_funcs(role) # 역할에 따른 기능 명시 분류
    name  = tool_call["name"]
    args  = json.loads(tool_call["arguments"])

    print(f"[LOG] tool 호출: {name}, args: {args}")

    func = funcs.get(name)
    if func is None:
        print(f"[LOG] 알 수 없는 함수: {name}")
        ans = "Error: 알 수 없는 함수입니다."
    else:
        try:
            ans = str(func(**args))
            print(f"[LOG] tool 결과: {ans[:100]}")
        except Exception as e:
            print(f"[LOG] tool 실행 오류: {e}")
            ans = f"Error: {e}"

    ## 일반 함수의 경우 테플릿을 사용
    if name == "calc":
        ans = calc_template(ans, args.get("a"), args.get("b"), args.get("c"))
    elif name == "get_time":
        ans = get_time_template(ans)

    msgs.append({"tool_call_id": tool_call["id"], "role": "tool", "name": name, "content": ans})
    return msgs

## [Step 3] 모든 tool 실행 완료 후 최종 LLM 응답 생성
def tool_finish(messages: list) -> str:
    return client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.7, top_p=0.7
    ).choices[0].message.content


## Rag Agent
def run_rag(user_input: str, n_results: int = 3) -> str:
    ## 질문 Vector화
    query_vector = vectorize_query(user_input)

    ## 관련 문서 검색
    results = collection.query(query_embeddings=[query_vector], n_results=n_results)
    context = "\n---\n".join(results["documents"][0])

    ## Context 포함하여 LLM 호출 (Tool 없음)
    msg = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user",   "content": f"[Context]\n{context}\n\n[질문]\n{user_input}"}
    ]
    return client.chat.completions.create(model="gpt-4o-mini", messages=msg).choices[0].message.content