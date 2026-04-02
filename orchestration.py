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

def run_orchestration(user_input: str, role: str, temperature: float = 0.7, top_p: float = 0.7) -> str:
    ## 역할에 따라 시스템 프롬프트 & 함수/Tool 목록 분리
    system_prompt = build_system_prompt(role)
    funcs = {**COMMON_FUNCS, **(ADMIN_FUNCS if role == "admin" else {})}
    tools = OPENAI_TOOLS + (VULN_OPENAI_TOOLS if role == "admin" else [])

    msg = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    ## 도구 선정
    res = client.chat.completions.create(model="gpt-4o-mini", messages=msg, tools=tools, temperature=temperature, top_p=top_p)

    msg.append(res.choices[0].message)

    ## 맨 마지막 배열의 tool을 통해 함수 호출
    if not msg[-1].tool_calls:
        return msg[-1].content
        
    for t in msg[-1].tool_calls:
        args = json.loads(t.function.arguments)

        print(f"[LOG] tool 호출: {t.function.name}, args: {args}")

        ## BUG FIX: funcs에 등록된 함수를 args로 올바르게 호출
        func = funcs.get(t.function.name)
        if func is None:
            print(f"[LOG] 알 수 없는 함수: {t.function.name}")
            ans = "Error: 알 수 없는 함수입니다."
        else:
            try:
                ans = str(func(**args))
                print(f"[LOG] tool 결과: {ans[:100]}")
            except Exception as e:
                print(f"[LOG] tool 실행 오류: {e}")
                ans = f"Error: {e}"

        ## 템플릿 역할
        if t.function.name == "calc":
            ans = calc_template(ans, args.get("a"), args.get("b"), args.get("c"))
        elif t.function.name == "get_time":
            ans = get_time_template(ans)
        
        msg.append({"tool_call_id": t.id, "role": "tool", "name": t.function.name, "content": ans})

    ## 최종 답변
    return client.chat.completions.create(model="gpt-4o-mini", messages=msg, temperature=temperature, top_p=top_p).choices[0].message.content


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