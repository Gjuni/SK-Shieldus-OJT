from multiAgent import app as agent_app
from fastapi import FastAPI, HTTPException
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

## 챗 API
@fast.post("/chat")
def chat(user_input: str) -> str:
    try:
        ## input 값에서 확인
        if check_input_prompt(user_input) == True:
            return "중요 정보 노출 가능성이 있는 프롬프트"
        if check_injection_by_rag(user_input) == True:
            return "중요 정보 노출 가능성이 있는 프롬프트"
        if moderation(user_input) == True:
            return "유해한 내용이 포함되어 있습니다."

        result = agent_app.invoke({ ## 챗봇 실행
            "user_input":   user_input,
            "role":         "",       # 역할 전달
            "routes":       [],
            "answers":      [],
            "final_answer": ""
        })

        ## output 값에서 확인
        if check_output_prompt(result["final_answer"]) == True:
            return "중요 정보 노출 가능성이 있는 프롬프트"
        if moderation(result["final_answer"]) == True:
            return "유해한 내용이 포함되어 있습니다."

        return result["final_answer"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

## 프론트 불러오기
@fast.get("/")
def index():
    return FileResponse("webView/main.html")

fast.mount("/webView", StaticFiles(directory="webView"), name="webView")

if __name__ == "__main__":
    uvicorn.run(fast, host="0.0.0.0", port=8000)