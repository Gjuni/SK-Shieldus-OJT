import json
from openai import OpenAI
from config.openAPI import OPENAI_API_KEY
from tool.tool import OPENAI_TOOLS, calc, get_time
from utility.template import calc_template, get_time_template

SYSTEM_PROMPT = """
당신은 사용자의 질문에 답변하는 AI 어시스턴트입니다.
사용자가 계산을 요청하면 calc 함수를 사용하세요. (a, b는 숫자 c는 연산자입니다.)
사용자가 시간을 요청하면 get_time 함수를 사용하세요. 
"""

client = OpenAI(api_key=OPENAI_API_KEY)

## 함수 정의
funcs = {"calc": calc, "get_time": get_time}

def run_orchestration(user_input: str) -> str:
    msg = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input}
        ]
        
    res = client.chat.completions.create(model="gpt-4o-mini", messages=msg, tools=OPENAI_TOOLS)

    msg.append(res.choices[0].message)
    
    print(msg)

    ## 맨 마지막 배열의 tool을 통해 함수 호출
    if not msg[-1].tool_calls:
        return msg[-1].content
        
    for t in msg[-1].tool_calls:
        args = json.loads(t.function.arguments)
        ans = str(funcs.get(t.function.name, lambda **_: "Error")(**args))

        if t.function.name == "calc":
            ans = calc_template(ans, args.get("a"), args.get("b"), args.get("c"))
        elif t.function.name == "get_time":
            ans = get_time_template(ans)
        msg.append({"tool_call_id": t.id, "role": "tool", "name": t.function.name, "content": ans})

    return client.chat.completions.create(model="gpt-4o-mini", messages=msg).choices[0].message.content
