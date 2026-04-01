from config.dbConnection import embedding_model

## 사용자 입력 Vector화
def vectorize_query(query: str) -> list:
    return embedding_model.encode(query).tolist()
