from multiAgent import app as agent_app
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

fast = FastAPI()

fast.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@fast.post("/chat")
def chat(user_input: str) -> str:
    try:
        result = agent_app.invoke({ ## 챗봇 실행
            "user_input":   user_input,
            "role":         "",       # 역할 전달
            "routes":       [],
            "answers":      [],
            "final_answer": ""
        })
        return result["final_answer"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@fast.get("/")
def index():
    return FileResponse("webView/main.html")

fast.mount("/webView", StaticFiles(directory="webView"), name="webView")

if __name__ == "__main__":
    uvicorn.run(fast, host="0.0.0.0", port=8000)