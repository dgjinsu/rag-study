"""대화형 질의 스크립트.

인덱싱된 Kubernetes 한국어 문서에 대해 질문하고 답변을 받는다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.retriever import query

console = Console()


def main() -> None:
    console.rule("[bold blue]Kubernetes 한국어 문서 RAG 질의")
    console.print("질문을 입력하세요. 종료하려면 'quit' 또는 'q'를 입력하세요.\n")

    while True:
        try:
            question = console.input("[bold cyan]질문> [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not question:
            continue
        if question.lower() in ("quit", "q", "exit"):
            break

        console.print()

        with console.status("[bold yellow]답변 생성 중...[/bold yellow]"):
            result = query(question)

        # 답변 출력
        console.print(Panel(Markdown(result["answer"]), title="답변", border_style="green"))

        # 참고 문서 출처 출력
        if result["sources"]:
            console.print("\n[dim]참고 문서:[/dim]")
            seen = set()
            for doc in result["sources"]:
                source = doc.metadata.get("source", "알 수 없음")
                if source not in seen:
                    seen.add(source)
                    title = doc.metadata.get("title", "")
                    console.print(f"  [dim]- {source}[/dim]" + (f" ({title})" if title else ""))
        console.print()

    console.print("\n[dim]종료합니다.[/dim]")


if __name__ == "__main__":
    main()
