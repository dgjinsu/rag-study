"""임베딩 + ChromaDB 저장 모듈.

Ollama에 비동기 동시 요청으로 임베딩을 병렬 처리하고,
ChromaDB에 저장한다.
"""

import asyncio

import httpx
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

from src.config import settings

# Ollama 서버에 동시에 보낼 수 있는 최대 요청 수
# GPU 성능에 따라 조절 (높을수록 빠르지만 서버 부하 증가)
MAX_CONCURRENCY = 20


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


async def _embed_all(texts: list[str], progress, task) -> list[list[float]]:
    """모든 텍스트를 동시에 임베딩한다.

    asyncio.gather로 모든 요청을 동시에 실행하되,
    Semaphore로 동시 실행 수를 MAX_CONCURRENCY로 제한한다.

    예: 528개 청크, MAX_CONCURRENCY=10이면
        → 10개씩 동시 요청, 나머지는 자리가 날 때까지 대기
        → 순차 처리 대비 최대 10배 빨라짐
    """
    # Semaphore: 동시에 실행할 수 있는 코루틴 수를 제한하는 잠금 장치
    # acquire()하면 카운트 -1, release()하면 +1, 0이면 대기
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    # 결과를 인덱스 순서대로 저장할 리스트 (gather는 완료 순서가 보장되지 않으므로)
    results: list[list[float]] = [[] for _ in texts]

    async with httpx.AsyncClient() as client:

        async def _request(i: int, text: str):
            async with semaphore:
                try:
                    resp = await client.post(
                        f"{settings.ollama_base_url}/api/embed",
                        json={"model": settings.embedding_model, "input": text},
                        timeout=120.0,
                    )
                    resp.raise_for_status()
                    results[i] = resp.json()["embeddings"][0]
                except httpx.HTTPStatusError:
                    # 텍스트가 너무 길면 앞부분만 잘라서 재시도
                    truncated = text[:500]
                    resp = await client.post(
                        f"{settings.ollama_base_url}/api/embed",
                        json={"model": settings.embedding_model, "input": truncated},
                        timeout=120.0,
                    )
                    resp.raise_for_status()
                    results[i] = resp.json()["embeddings"][0]
                progress.advance(task)

        # 모든 텍스트에 대한 코루틴을 한번에 생성하고 동시 실행
        # gather는 모든 코루틴이 완료될 때까지 대기
        await asyncio.gather(*[_request(i, t) for i, t in enumerate(texts)])

    return results


def index_documents(chunks: list[Document]) -> Chroma:
    """청크 리스트를 병렬 임베딩하여 ChromaDB에 저장한다."""
    texts = [c.page_content for c in chunks]
    metadatas = [c.metadata for c in chunks]

    # rich Progress: 터미널에 진행 바를 표시
    with Progress(
        SpinnerColumn(),          # ⠋ 회전 애니메이션
        TextColumn("[bold blue]{task.description}"),  # "임베딩 중..."
        BarColumn(),              # 진행 바
        TextColumn("{task.completed}/{task.total}"),   # 350/528
        TimeElapsedColumn(),      # 0:01:23 경과 시간
    ) as progress:
        task = progress.add_task("임베딩 중...", total=len(chunks))
        # 비동기 함수를 동기 컨텍스트에서 실행
        embeddings = asyncio.run(_embed_all(texts, progress, task))

    # 임베딩 완료 후 ChromaDB에 저장
    vector_store = Chroma(
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )
    # upsert: 같은 id가 있으면 덮어쓰기, 없으면 새로 추가
    vector_store._collection.upsert(
        ids=[f"chunk_{i}" for i in range(len(chunks))],
        documents=texts,        # 원문 텍스트 (검색 결과에서 보여줄 용도)
        embeddings=embeddings,  # 벡터 (유사도 검색에 사용)
        metadatas=metadatas,    # 메타데이터 (source, title, header 등)
    )

    return vector_store
