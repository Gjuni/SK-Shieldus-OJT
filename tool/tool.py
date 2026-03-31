from datetime import datetime

## 계산기
def calc(a, b, c) :
    if(c == "+") :
        return a + b
    elif(c == "-") :
        return a - b
    elif(c == "*") :
        return a * b
    elif(c == "/") :
        return a / b
    else :
        return "잘못된 연산자입니다."
    
## 현재 시간 보기
def get_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

## 함수 정의
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "사용자가 계산을 요청할 때 사용하는 함수구현체",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {
                        "type": "number",
                        "description": "첫번째 숫자"
                    },
                    "b": {
                        "type": "number",
                        "description": "두번째 숫자"
                    },
                    "c": {
                        "type": "string",
                        "description": "연산자 (+, -, *, /)"
                    }
                },
                "required": ["a", "b", "c"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "사용자가 시간을 요청할 때 사용하는 함수구현체",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]