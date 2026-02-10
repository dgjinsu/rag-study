"""마크다운 문서 로딩 모듈.

docs/k8s-ko/ 폴더에서 .md 파일들을 재귀적으로 로드한다.
각 Document에 source(파일 경로)와 title 메타데이터를 추가한다.
"""

import re
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document

from src.config import settings


def _extract_title(content: str) -> str:
    """마크다운 내용에서 첫 번째 h1 헤더를 추출한다."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _clean_frontmatter(content: str) -> str:
    """YAML front matter (--- ... ---) 를 제거한다."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)


def load_documents(docs_dir: str | None = None) -> list[Document]:
    """마크다운 문서들을 로드한다.

    Args:
        docs_dir: 문서 디렉토리 경로. None이면 설정값 사용.

    Returns:
        Document 리스트. 각 Document는 page_content와 metadata를 가짐.
    """
    docs_path = Path(docs_dir) if docs_dir else settings.docs_path

    if not docs_path.exists():
        raise FileNotFoundError(
            f"문서 디렉토리가 존재하지 않습니다: {docs_path}\n"
            "먼저 scripts/download_docs.py를 실행하세요."
        )

    loader = DirectoryLoader(
        str(docs_path),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,
    )
    raw_docs = loader.load()

    # front matter 제거 및 title 메타데이터 추가
    documents = []
    for doc in raw_docs:
        cleaned_content = _clean_frontmatter(doc.page_content)
        if not cleaned_content.strip():
            continue

        title = _extract_title(cleaned_content)
        doc.page_content = cleaned_content
        doc.metadata["title"] = title or Path(doc.metadata.get("source", "")).stem

        documents.append(doc)

    return documents
