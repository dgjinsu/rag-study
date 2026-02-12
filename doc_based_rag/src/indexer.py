"""임베딩 + ChromaDB 저장 모듈.

sentence-transformers로 로컬 임베딩을 수행하고,
ChromaDB에 저장한다.
"""

import torch
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from sentence_transformers import SentenceTransformer

from src.config import settings

console = Console()

# sentence-transformers encode() 시 배치 크기
BATCH_SIZE = 64
# GPU 사용 가능 여부 확인
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def get_embeddings() -> HuggingFaceEmbeddings:
    """HuggingFace 임베딩 모델을 반환한다. (LangChain 호환)"""
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        model_kwargs={"device": DEVICE},
    )


def get_vector_store() -> Chroma:
    """기존 ChromaDB 벡터 스토어를 로드한다."""
    return Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def _embed_all(texts: list[str], progress, task) -> list[list[float]]:
    """sentence-transformers로 모든 텍스트를 임베딩한다.

    GPU가 있으면 자동으로 GPU를 사용하고,
    내부적으로 배치 처리하여 메모리를 효율적으로 관리한다.
    """
    model = SentenceTransformer(settings.embedding_model, device=DEVICE)
    console.print(f"  디바이스: [bold]{DEVICE.upper()}[/bold]")

    all_embeddings = []
    # 배치 단위로 나눠서 진행 바를 업데이트
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_embeddings = model.encode(batch, show_progress_bar=False)
        all_embeddings.extend(batch_embeddings.tolist())
        progress.advance(task, len(batch))

    return all_embeddings


def index_documents(chunks: list[Document]) -> Chroma:
    """청크 리스트를 임베딩하여 ChromaDB에 저장한다."""
    texts = [c.page_content for c in chunks]
    metadatas = [c.metadata for c in chunks]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("임베딩 중...", total=len(chunks))
        embeddings = _embed_all(texts, progress, task)

    # ChromaDB에 저장
    vector_store = Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )
    vector_store._collection.upsert(
        ids=[f"chunk_{i}" for i in range(len(chunks))],
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return vector_store
