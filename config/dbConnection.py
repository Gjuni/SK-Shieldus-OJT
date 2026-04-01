import chromadb
from dotenv import load_dotenv
import os
from sentence_transformers import SentenceTransformer

load_dotenv()

api_key = os.getenv("cromadb")
tenant = os.getenv("tenant")
database = os.getenv("database")
collection_name = os.getenv("collection")

client = chromadb.CloudClient(
  api_key=api_key,
  tenant=tenant,
  database=database
)

collection = client.get_or_create_collection(collection_name)

# HuggingFace 임베딩 모델 로드
embedding_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# metadata 폴더의 txt 파일 목록 (idx 1~5 순서 고정)
METADATA_FILES = [
    "FAQ.txt",
    "LLM동작체감하기.txt",
    "LLM시스템구조익히기.txt",
    "huggingFace.txt",
    "벡터DB 및 RAG 구축.txt",
]

def chunk_text(text: str, chunk_size: int = 12000) -> list:
    """텍스트를 chunk_size(bytes) 단위로 분할합니다."""
    chunks = []
    encoded = text.encode("utf-8")
    for i in range(0, len(encoded), chunk_size):
        chunk_bytes = encoded[i:i + chunk_size]
        chunks.append(chunk_bytes.decode("utf-8", errors="ignore"))
    return chunks


def addData():
    """
    metadata 폴더의 5개 txt 파일을 HuggingFace 임베딩으로 변환하여 ChromaDB에 삽입합니다.
    각 파일의 idx는 1~5로 고정되며, 16KB 초과 파일은 자동으로 청킹하여 분할 삽입합니다.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    metadata_dir = os.path.join(base_dir, "..", "metadata")

    for idx, filename in enumerate(METADATA_FILES, start=1):
        file_path = os.path.join(metadata_dir, filename)

        if not os.path.exists(file_path):
            print(f"[경고] 파일을 찾을 수 없습니다: {file_path}")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 파일 크기 확인 (ChromaDB 무료 플랜: 16384 bytes 제한)
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > 14000:
            # 청킹 처리: doc_4_0, doc_4_1, ... 형식으로 분할 삽입
            chunks = chunk_text(content)
            print(f"[{idx}/5] '{filename}' → 크기 {content_bytes}bytes, {len(chunks)}개 청크로 분할 삽입 중...")
            for chunk_idx, chunk in enumerate(chunks):
                doc_id = f"doc_{idx}_{chunk_idx}"
                embedding = embedding_model.encode(chunk).tolist()
                collection.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    embeddings=[embedding],
                    metadatas=[{"idx": idx, "filename": filename, "chunk": chunk_idx}]
                )
                print(f"  └ 청크 {chunk_idx} 삽입 완료 (id: {doc_id})")
        else:
            # 단일 문서 삽입
            doc_id = f"doc_{idx}"
            embedding = embedding_model.encode(content).tolist()
            collection.upsert(
                ids=[doc_id],
                documents=[content],
                embeddings=[embedding],
                metadatas=[{"idx": idx, "filename": filename}]
            )
            print(f"[{idx}/5] '{filename}' 삽입 완료 (id: {doc_id})")

    print("\n 모든 데이터 삽입이 완료되었습니다.")



def get_context(query: str) -> str:
    embedding = embedding_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=3
    )
    
    context = ""
    for doc in results['documents'][0]:
        context += doc + "\n"
    return context
