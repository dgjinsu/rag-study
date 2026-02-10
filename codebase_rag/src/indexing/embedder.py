"""
임베딩 모듈.

Ollama를 사용하여 청크 텍스트를 로컬에서 벡터로 변환한다.
외부 API 비용 없이 무료로 임베딩할 수 있다.

사전 준비:
    1. Ollama 설치: https://ollama.com
    2. 모델 다운로드: ollama pull nomic-embed-text

사용 예:
    embedder = Embedder()
    results = embedder.embed_chunks(chunks)  # [(chunk, vector), ...]
"""

from __future__ import annotations

import httpx

from src.models import Chunk


class Embedder:
    """Ollama 임베딩 API 래퍼."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ):
        self.base_url = base_url
        self.model = model

    def embed_chunks(
        self,
        chunks: list[Chunk],
    ) -> list[tuple[Chunk, list[float]]]:
        """
        청크 리스트를 임베딩하여 (chunk, vector) 쌍을 반환한다.

        Ollama API를 개별 호출한다 (배치 미지원).

        Args:
            chunks: 임베딩할 Chunk 리스트.

        Returns:
            (Chunk, embedding_vector) 튜플 리스트.
        """
        results: list[tuple[Chunk, list[float]]] = []
        total = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            vector = self._embed_single(chunk.chunk_text)
            results.append((chunk, vector))

            if i % 50 == 0 or i == total:
                print(f"  임베딩 진행 [{i}/{total}]")

        return results

    def embed_query(self, query: str) -> list[float]:
        """
        단일 검색 쿼리를 임베딩한다.

        Args:
            query: 검색 쿼리 텍스트.

        Returns:
            임베딩 벡터.
        """
        return self._embed_single(query)

    def _embed_single(self, text: str) -> list[float]:
        """
        단일 텍스트를 Ollama API로 임베딩한다.

        Args:
            text: 임베딩할 텍스트.

        Returns:
            임베딩 벡터.
        """
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": text},
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"][0]
