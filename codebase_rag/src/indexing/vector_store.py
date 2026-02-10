"""
벡터 저장소 모듈.

ChromaDB를 사용하여 청크 임베딩을 저장하고 검색한다.
메타데이터 필터링을 지원하며, upsert 기반으로 증분 업데이트가 가능하다.

사용 예:
    store = VectorStore(persist_dir="data/chroma_db")
    store.upsert_chunks(chunks, embeddings)
    results = store.search(query_vector, n_results=10)
"""

from __future__ import annotations

import chromadb

from src.models import Chunk


class VectorStore:
    """ChromaDB 컬렉션을 관리한다."""

    def __init__(
        self,
        persist_dir: str = "data/chroma_db",
        collection_name: str = "codebase",
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """
        청크와 임베딩을 ChromaDB에 upsert한다.

        같은 chunk_id가 이미 존재하면 덮어쓴다.
        ChromaDB의 upsert 배치 제한에 맞춰 분할 처리한다.

        Args:
            chunks: Chunk 리스트.
            embeddings: 대응되는 임베딩 벡터 리스트.

        Returns:
            upsert된 문서 수.
        """
        batch_size = 500  # ChromaDB 권장 배치 크기
        total = 0

        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i : i + batch_size]
            batch_embeddings = embeddings[i : i + batch_size]

            ids = [c.chunk_id for c in batch_chunks]
            documents = [c.chunk_text for c in batch_chunks]
            metadatas = [self._chunk_to_metadata(c) for c in batch_chunks]

            self.collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=batch_embeddings,
                metadatas=metadatas,
            )
            total += len(batch_chunks)

        return total

    def search(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
        where_document: dict | None = None,
    ) -> list[dict]:
        """
        벡터 유사도 검색을 수행한다.

        Args:
            query_embedding: 쿼리 벡터.
            n_results: 반환할 결과 수.
            where: 메타데이터 필터 (예: {"entity_type": "method"}).
            where_document: 문서 내용 필터 (예: {"$contains": "@Transactional"}).

        Returns:
            검색 결과 리스트. 각 항목은 id, document, metadata, distance를 포함.
        """
        query_params: dict = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            query_params["where"] = where
        if where_document:
            query_params["where_document"] = where_document

        raw = self.collection.query(**query_params)

        # ChromaDB 결과를 딕셔너리 리스트로 변환
        results: list[dict] = []
        if raw["ids"] and raw["ids"][0]:
            for i in range(len(raw["ids"][0])):
                results.append({
                    "id": raw["ids"][0][i],
                    "document": raw["documents"][0][i] if raw["documents"] else None,
                    "metadata": raw["metadatas"][0][i] if raw["metadatas"] else None,
                    "distance": raw["distances"][0][i] if raw["distances"] else None,
                })

        return results

    def delete_by_file(self, file_path: str) -> None:
        """
        특정 파일에 속한 모든 청크를 삭제한다.

        Args:
            file_path: 삭제할 파일 경로.
        """
        self.collection.delete(where={"file_path": file_path})

    def get_collection_stats(self) -> dict:
        """컬렉션 통계를 반환한다."""
        return {
            "name": self.collection.name,
            "count": self.collection.count(),
        }

    @staticmethod
    def _chunk_to_metadata(chunk: Chunk) -> dict:
        """
        Chunk 객체를 ChromaDB 메타데이터 딕셔너리로 변환한다.

        ChromaDB는 str, int, float, bool만 허용하므로
        리스트 필드는 쉼표 구분 문자열로 변환한다.
        """
        return {
            "entity_type": chunk.entity_type,
            "name": chunk.name,
            "qualified_name": chunk.qualified_name,
            "file_path": chunk.file_path,
            "class_name": chunk.class_name or "",
            "package_name": chunk.package_name or "",
            "return_type": chunk.return_type or "",
            "annotations": ",".join(chunk.annotations),
            "modifiers": ",".join(chunk.modifiers),
            "parameters": ",".join(chunk.parameters),
            "calls": ",".join(chunk.calls),
            "called_by": ",".join(chunk.called_by),
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "part_index": chunk.part_index,
            "total_parts": chunk.total_parts,
        }
