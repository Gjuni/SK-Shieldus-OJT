from multiAgent import app

while (user_input := input("\n입력 (종료: quit): ")) != 'quit':
    if user_input.strip():
        result = app.invoke({
            "user_input":   user_input,
            "routes":       [],
            "answers":      [],
            "final_answer": ""
        })
        print(result["final_answer"])
