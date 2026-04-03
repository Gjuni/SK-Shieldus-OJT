from config.dbConnection import injection_collection, embedding_model

## 유사도 임계값: 이 값 이상이면 프롬프트 인젝션으로 판단
INJECTION_THRESHOLD = 0.85

def check_injection_by_rag(text: str) -> bool:
    try:
        # 입력 벡터화
        query_vector = embedding_model.encode(text).tolist()

        # 가장 유사한 공격 문장 1개 검색
        results = injection_collection.query(
            query_embeddings=[query_vector],
            n_results=1,
            include=["documents", "distances"]
        )

        if not results["distances"] or not results["distances"][0]:
            return False

        # ChromaDB는 코사인 거리(0=완전일치, 2=완전반대)를 반환
        # 유사도 = 1 - (distance / 2)
        distance = results["distances"][0][0]
        similarity = 1 - (distance / 2)

        matched_doc = results["documents"][0][0] if results["documents"][0] else ""
        print(f"[RAG Guard] 유사도: {similarity:.4f} | 매칭 문장: {matched_doc[:60]}")

        return similarity >= INJECTION_THRESHOLD

    except Exception as e:
        print(f"[RAG Guard] 오류 발생: {e}")
        return False  # 오류 시 차단하지 않음 (서비스 가용성 우선)
