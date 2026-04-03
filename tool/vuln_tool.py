import os
import subprocess
from secure.tool_verify import SANDBOX_DIR, shell_exec_verify, python_eval_verify, write_file_verify

def shell_exec(command: str) -> str:
    if not isinstance(command, str):
        return "잘못된 입력입니다."
    
    if shell_exec_verify(command):
        return "사용할 수 있는 shell 명령어는 data, clear, ls, cat입니다."

    ## BUG: os.system()은 exit code만 반환 → subprocess로 변경해야 stdout 캡처 가능
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=SANDBOX_DIR)

    return result.stdout + result.stderr

## ?뚯씠??eval ??SandBox ?붾젆?좊━ ??subprocess濡?寃⑸━ ?ㅽ뻾
def python_eval(expr: str) -> str:
    if not isinstance(expr, str):
        return "잘못된 입력입니다."

    if python_eval_verify(expr):
        return "허용되지 않은 Python 표현식입니다."

    result = subprocess.run(
        ["python", "-c", f"print({expr})"],
        capture_output=True, text=True, timeout=5,
        cwd=SANDBOX_DIR  
    )

    if python_eval_verify(expr):
        return "허용되지 않은 Python 표현식입니다."

    return (result.stdout + result.stderr).strip()


def write_file(path: str, content: str) -> str:
    if not isinstance(path, str) or not isinstance(content, str):
        return "잘못된 입력입니다."
    
    if write_file_verify(path):
        return "허용되지 않은 경로 및 확장자 입니다."

    full_path = os.path.join(SANDBOX_DIR, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w") as f:
        f.write(content)
    return f"{full_path}에 저장했습니다."


## 파일 읽기 → path에서 파일명만 추출해 SANDBOX_DIR 고정
def read_file(path: str) -> str:
    if not isinstance(path, str):
        return "잘못된 입력입니다."

    ## basename으로 디렉토리 부분 제거 → 파일명만 SANDBOX_DIR에 결합
    full_path = os.path.join(SANDBOX_DIR, os.path.basename(path))

    if not os.path.isfile(full_path):
        candidates = sorted(
            [name for name in os.listdir(SANDBOX_DIR) if os.path.isfile(os.path.join(SANDBOX_DIR, name))]
        )
        return (
            f"요청한 파일을 찾을 수 없습니다: {os.path.basename(path)}\n"
            f"Sandbox 파일 목록: {', '.join(candidates) if candidates else '(비어 있음)'}"
        )

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()

# ## DB 설정은 하지 않았지만.. 그래도 구현 config에서 DB 접속 정보를 불러와야함.
# def db_query(query: str) -> str:
#     if query is not str:
#         return "잘못된 입력입니다."
    
#     ## 사용자 검증을 타입으로만 받고 내부 query 값은 검증하는 로직 X 바로 실행
#     return db.query(query)


## 함수 정의
VULN_OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "사용자가 요청한 쉘 명령어를 실행하는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "실행할 쉘 명령어 (예: ls, whoami, cat /etc/passwd)"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "python_eval",
            "description": "사용자가 요청한 파이썬 코드를 실행하는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "expr": {
                        "type": "string",
                        "description": "실행할 파이썬 표현식 (예: 1+1, __import__('os').getcwd())"
                    }
                },
                "required": ["expr"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "사용자가 지정한 경로에 파일을 쓰는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "파일을 저장할 경로 (예: ./output.txt, /etc/cron.d/backdoor)"
                    },
                    "content": {
                        "type": "string",
                        "description": "파일에 쓸 내용"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "사용자가 지정한 경로의 파일을 읽는 함수",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "읽을 파일의 경로 (예: ./secret.txt, /etc/passwd)"
                    }
                },
                "required": ["path"]
            }
        }
    }
]