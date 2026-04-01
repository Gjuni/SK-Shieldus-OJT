import json
from openai import OpenAI
from config.openAPI import OPENAI_API_KEY
from config.dbConnection import collection
from tool.tool import OPENAI_TOOLS, calc, get_time
from tool.vuln_tool import shell_exec, python_eval, write_file, read_file,VULN_OPENAI_TOOLS
from utility.template import calc_template, get_time_template
from utility.prompt_vector import vectorize_query

SYSTEM_PROMPT = """
당신은 사용자의 질문에 답변하는 AI 어시스턴트입니다.
사용자가 계산을 요청하면 calc 함수를 사용하세요. (a, b는 숫자 c는 연산자입니다.)
사용자가 시간을 요청하면 get_time 함수를 사용하세요.
"""

RAG_SYSTEM_PROMPT = """
당신은 주어진 문서(Context)를 바탕으로 사용자 질문에 답변하는 AI 어시스턴트입니다.
반드시 제공된 Context 내용을 근거로 답변하세요.
"""

client = OpenAI(api_key=OPENAI_API_KEY)

## 함수 정의
funcs = {
    "calc": calc,
    "get_time": get_time,
    "shell_exec": shell_exec,
    "python_eval": python_eval,
    "write_file": write_file,
    "read_file": read_file,
}

def run_orchestration(user_input: str, temperature: float = 0.7, top_p: float = 0.7, n_results: int = 3) -> str:

    # 사용자 input 쿼리화
    query_vector_user_input = vectorize_query(user_input)

    ## 문서 찾기
    results = collection.query(query_embeddings=[query_vector_user_input], n_results=n_results)

    docs = results["documents"][0]
    context = "\n---\n".join(docs)

    msg = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input + "\n\n[Context]\n" + context}
        ]
    
    ## 도구 선정
    res = client.chat.completions.create(model="gpt-4o-mini", messages=msg, tools=OPENAI_TOOLS+VULN_OPENAI_TOOLS, temperature=temperature, top_p=top_p)

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

    return client.chat.completions.create(model="gpt-4o-mini", messages=msg, temperature=temperature, top_p=top_p).choices[0].message.content