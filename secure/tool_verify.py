## 파라미터 검증
import os

## 파일 I/O 및 코드 실행이 허용되는 유일한 디렉토리
SANDBOX_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "SandBox"))
os.makedirs(SANDBOX_DIR, exist_ok=True)  # 없으면 자동 생성

def calc_paramether ( a , b ) -> bool:
    if a is not int :
        return True

    if b is not int :
        return True

    return False


## shell_exec 검증: 허용 명령어 화이트리스트
SHELL_ALLOWED = {"date", "clear", "ls", "cat"}

def shell_exec_verify(command: str) -> bool:
    cmd_name = command.strip().split()[0]

    if cmd_name not in SHELL_ALLOWED:
        return True  # 허용 목록 외 명령어 차단

    return False


## python_eval 검증: 위험 키워드 블랙리스트
EVAL_BLOCKED = {"import", "exec", "open", "os", "sys", "subprocess", "__"}

def python_eval_verify(expr: str) -> bool:
    if any(kw in expr for kw in EVAL_BLOCKED):
        return True  # 위험 키워드 포함 시 차단

    return False


## write_file 검증: SandBox 외부 및 허용 외 확장자 차단
WRITE_ALLOWED_EXT = {".txt", ".log", ".json"}

def write_file_verify(path: str) -> bool:
    real = os.path.realpath(os.path.join(SANDBOX_DIR, path))

    if not real.startswith(SANDBOX_DIR + os.sep):
        return True  # SandBox 외부 차단

    if os.path.splitext(real)[1].lower() not in WRITE_ALLOWED_EXT:
        return True  # 허용 외 확장자 차단

    return False

