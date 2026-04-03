from multiAgent import app as agent_app, MAX_GRAPH_ITERATIONS
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from secure.moderation import moderation
from secure.regix import check_input_prompt, check_output_prompt
from secure.rag_guard import check_injection_by_rag
import uvicorn

fast = FastAPI()

fast.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@fast.post("/chat")
def chat(request: Request, user_input: str, confirm_risky_tools: bool = False) -> str:
    try:
        if check_input_prompt(user_input):
            return "Prompt may leak sensitive information."
        if check_injection_by_rag(user_input):
            return "Prompt may leak sensitive information."
        if moderation(user_input):
            return "Harmful content detected."

        result = agent_app.invoke(
            {
                "user_input": user_input,
                "role": "",
                "routes": [],
                "answers": [],
                "final_answer": "",
                "tool_messages": [],
                "pending_tool_calls": [],
                "confirm_risky_tools": confirm_risky_tools,
            },
            {"recursion_limit": MAX_GRAPH_ITERATIONS},
        )

        if check_output_prompt(result["final_answer"]):
            return "Prompt may leak sensitive information."
        if moderation(result["final_answer"]):
            return "Harmful content detected."

        return result["final_answer"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fast.get("/")
def index():
    return FileResponse("webView/main.html")


fast.mount("/webView", StaticFiles(directory="webView"), name="webView")

if __name__ == "__main__":
    uvicorn.run(fast, host="0.0.0.0", port=8000)
