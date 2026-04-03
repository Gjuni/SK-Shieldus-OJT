# SK-Shieldus-OJT
On the Job Training Sk Shieldus

[OPEN API docs](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)

파일 관리
--
config : 각종 설정 파일 (OPEN API, Vector DB 등등)

uility : Safety Filtering, Prompt Template

tool : Tool calling 시 Tool 정의 및 실행

webview : HTML 프롬프트 입력


LLM 정의
--
orchestration.py : LLM 호출 및 관리


Convention
--
Issue : 해당 산출물 내용

Branch : OJT-Day-XX

Pull Request : [OJT] Day XX


File Architecture
--

SK-Shieldus-OJT/
├── app.py                    ← FastAPI 메인 서버 (진입점)
├── multiAgent.py             ← LangGraph 멀티 에이전트 오케스트레이터
├── orchestration.py          ← LLM 호출 + Tool 실행
│
├── config/
│   ├── openAPI.py            ← OpenAI API 키 로딩
│   └── dbConnection.py       ← ChromaDB 연결 + 벡터 임베딩
│
├── secure/
│   ├── moderation.py         ← OpenAI Moderation API (유해 콘텐츠 필터)
│   ├── regix.py              ← 정규식 기반 프롬프트 인젝션 차단
│   └── rag_guard.py          ← RAG 유사도 기반 인젝션 탐지
│
├── tool/
│   ├── tool.py               ← 공용 함수 (계산, 시간) [user + admin]
│   └── vuln_tool.py          ← 위험 함수 (파일, 쉘, eval) [admin only]
│
├── utility/
│   ├── template.py           ← 응답 포맷팅
│   └── prompt_vector.py      ← 텍스트 → 벡터 변환
│
├── webView/
│   └── main.html             ← 다크 테마 채팅 UI
│
└── metadata/
    ├── FAQ.txt
    ├── LLM동작체감하기.txt
    ├── LLM시스템구조익히기.txt
    ├── huggingFace.txt
    ├── 벡터DB 및 RAG 구축.txt
    └── LeakSYSTEMPROMPT.txt  ← 인젝션 공격 샘플 (보안용 학습 데이터)
