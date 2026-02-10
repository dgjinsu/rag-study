"""문서 인덱싱 파이프라인 실행 스크립트.

문서 로딩 → 청킹 → 임베딩 → ChromaDB 저장 전체 과정을 실행한다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

from src.chunker import chunk_documents
from src.indexer import index_documents
from src.loader import load_documents

console = Console()


def main() -> None:
    console.rule("[bold blue]Kubernetes 한국어 문서 인덱싱")

    # 1. 문서 로딩
    console.print("\n[1/3] 마크다운 문서를 로딩합니다...")
    documents = load_documents()
    console.print(f"  로드된 문서 수: [green]{len(documents)}[/green]")

    if not documents:
        console.print("[red]로드된 문서가 없습니다. 먼저 download_docs.py를 실행하세요.[/red]")
        return

    # 2. 문서 청킹
    console.print("\n[2/3] 문서를 청크로 분할합니다...")
    chunks = chunk_documents(documents)
    console.print(f"  생성된 청크 수: [green]{len(chunks)}[/green]")

    # 청크 통계
    lengths = [len(c.page_content) for c in chunks]
    console.print(f"  청크 길이 (평균/최소/최대): {sum(lengths)//len(lengths)} / {min(lengths)} / {max(lengths)}")

    # 3. 임베딩 + 벡터 저장
    console.print("\n[3/3] 임베딩 생성 및 ChromaDB에 저장합니다...")
    console.print("  (Ollama 서버가 실행 중이어야 합니다)")
    vector_store = index_documents(chunks)

    collection_count = vector_store._collection.count()
    console.print(f"  ChromaDB 저장 완료: [green]{collection_count}[/green]개 문서")

    console.rule("[bold green]인덱싱 완료")
    console.print("\n이제 scripts/run_query.py로 질의할 수 있습니다.\n")


if __name__ == "__main__":
    main()
