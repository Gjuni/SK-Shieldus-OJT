from orchestration import run_orchestration
from utility.template import apply_template

while (user_input := input("\n입력 (종료: quit): ")) != 'quit':
    if user_input.strip():
        print(apply_template(run_orchestration(user_input)))
