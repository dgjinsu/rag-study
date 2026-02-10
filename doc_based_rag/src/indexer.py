"""임베딩 + ChromaDB 저장 모듈.

LangChain의 OllamaEmbeddings와 Chroma를 사용하여
문서 청크를 벡터화하고 ChromaDB에 저장한다.
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from src.config import settings


def get_embeddings() -> OllamaEmbeddings:
    """Ollama 임베딩 모델을 반환한다."""
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
    )


def get_vector_store() -> Chroma:
    """기존 ChromaDB 벡터 스토어를 로드한다."""
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def index_documents(chunks: list[Document]) -> Chroma:
    """청크 리스트를 임베딩하여 ChromaDB에 저장한다.

    Args:
        chunks: 분할된 Document 리스트.

    Returns:
        생성된 Chroma 벡터 스토어.
    """
    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        collection_name=settings.chroma_collection,
        persist_directory=settings.chroma_persist_dir,
    )
    return vector_store
