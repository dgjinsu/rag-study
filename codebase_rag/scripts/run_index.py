"""
인덱싱 파이프라인 실행 스크립트.

전체 흐름:
    Java 파일 수집 → 파싱 → 호출 그래프 해석 → 청킹 → 임베딩 → ChromaDB 저장

사용법:
    python scripts/run_index.py
"""

import sys
from collections import Counter
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings
from src.parsing.java_parser import JavaParser
from src.parsing.extractors import EntityExtractor
from src.parsing.call_graph import CallGraph
from src.chunking.chunker import Chunker
from src.indexing.embedder import Embedder
from src.indexing.vector_store import VectorStore


def main():
    settings = Settings()

    # ── 1단계: 파싱 ────────────────────────────────────────
    java_root = settings.java_project_path / "src" / "main" / "java"
    java_files = sorted(java_root.rglob("*.java"))
    print(f"Java 파일 수: {len(java_files)}개")
    print("=" * 60)

    parser = JavaParser()
    extractor = EntityExtractor()
    all_entities = []

    for i, java_file in enumerate(java_files, 1):
        tree, source = parser.parse_file(java_file)
        entities = extractor.extract(tree, source, java_file)
        all_entities.extend(entities)
        print(f"[{i}/{len(java_files)}] {java_file.name} → {len(entities)}개 엔티티")

    print("=" * 60)
    print(f"총 엔티티: {len(all_entities)}개")

    # ── 2단계: 호출 그래프 해석 ─────────────────────────────
    graph = CallGraph()
    graph.resolve_invocations(all_entities)
    print("호출 그래프 해석 완료")
    print()

    # ── 3단계: 청킹 ────────────────────────────────────────
    print("── 청킹 시작 ──")
    chunker = Chunker(max_chunk_lines=settings.max_chunk_lines)
    chunks = chunker.chunk_entities(all_entities)

    type_counts = Counter(c.entity_type for c in chunks)
    print(f"총 청크: {len(chunks)}개")
    for entity_type, count in type_counts.most_common():
        print(f"  {entity_type:12}: {count}개")

    split_count = sum(1 for c in chunks if c.total_parts > 1)
    if split_count:
        print(f"  (분할된 메서드 파트: {split_count}개)")
    print()

    # ── 4단계: 임베딩 (Ollama 로컬) ─────────────────────────
    print("── 임베딩 시작 (Ollama) ──")
    embedder = Embedder(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
    )
    results = embedder.embed_chunks(chunks)
    print(f"임베딩 완료: {len(results)}개 벡터 생성")
    print()

    # ── 5단계: ChromaDB 저장 ────────────────────────────────
    print("── ChromaDB 저장 시작 ──")
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.chroma_collection_name,
    )

    chunks_ordered = [chunk for chunk, _ in results]
    embeddings = [emb for _, emb in results]
    upserted = store.upsert_chunks(chunks_ordered, embeddings)

    stats = store.get_collection_stats()
    print(f"저장 완료: {upserted}개 upsert")
    print(f"컬렉션 '{stats['name']}' 총 문서 수: {stats['count']}개")
    print()
    print("인덱싱 파이프라인 완료!")


if __name__ == "__main__":
    main()
