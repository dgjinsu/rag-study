"""마크다운 문서 로딩 모듈.

docs/k8s-ko/ 폴더에서 .md 파일들을 재귀적으로 로드한다.
각 Document에 source(파일 경로)와 title 메타데이터를 추가한다.
K8s 문서의 Hugo 템플릿 태그, HTML 태그 등 노이즈를 제거한다.
"""

import re
from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_core.documents import Document

from src.config import settings

# 최소 문서 길이 (이보다 짧으면 스킵)
MIN_DOC_LENGTH = 50


def _extract_title(content: str) -> str:
    """마크다운 내용에서 첫 번째 h1 헤더를 추출한다."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def _clean_frontmatter(content: str) -> str:
    """YAML front matter (--- ... ---) 를 제거한다."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)


def _clean_hugo_tags(content: str) -> str:
    """K8s 문서의 Hugo 템플릿 태그를 정리한다."""
    # glossary_tooltip: 텍스트만 추출
    # {{< glossary_tooltip text="파드" term_id="pod" >}} → 파드
    content = re.sub(
        r'\{\{<\s*glossary_tooltip\s+text="([^"]+)"[^>]*>\}\}',
        r"\1",
        content,
    )
    # glossary_tooltip: term_id가 먼저 오는 경우
    content = re.sub(
        r'\{\{<\s*glossary_tooltip\s+term_id="[^"]+"\s+text="([^"]+)"[^>]*>\}\}',
        r"\1",
        content,
    )

    # heading 태그: 텍스트만 추출
    # {{% heading "whatsnext" %}} → 다음 내용
    heading_map = {
        "whatsnext": "다음 내용",
        "objectives": "목표",
        "prerequisites": "사전 준비",
        "cleanup": "정리",
    }
    def _replace_heading(m: re.Match) -> str:
        key = m.group(1)
        return heading_map.get(key, key)
    content = re.sub(r'\{{% heading "([^"]+)" %\}\}', _replace_heading, content)

    # note, warning, caution 블록: 내용만 유지
    # {{< note >}} 내용 {{< /note >}} → 내용
    content = re.sub(r"\{\{<\s*/?(note|warning|caution)\s*>\}\}", "", content)

    # code_sample, codenew: 파일 경로만 남기기
    # {{% code_sample file="example.yaml" %}} → (코드: example.yaml)
    content = re.sub(
        r'\{\{[<%]\s*code(?:_sample|new)\s+file="([^"]+)"[^>%]*[>%]\}\}',
        r"(코드: \1)",
        content,
    )

    # include, version-check 등 나머지 태그: 제거
    content = re.sub(r"\{\{[<&%].*?[>&%]\}\}", "", content)

    return content


def _clean_html(content: str) -> str:
    """HTML 태그와 주석을 제거한다."""
    # HTML 주석
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    # <br>, <br/>, <hr> 등 self-closing 태그
    content = re.sub(r"<(?:br|hr)\s*/?>", "\n", content, flags=re.IGNORECASE)
    # <div>, </div> 등 블록 태그 (내용은 유지)
    content = re.sub(r"</?(?:div|span|p|table|tr|td|th|thead|tbody)[^>]*>", "", content, flags=re.IGNORECASE)
    # <a href="...">텍스트</a> → 텍스트
    content = re.sub(r"<a\s[^>]*>(.*?)</a>", r"\1", content, flags=re.DOTALL | re.IGNORECASE)
    return content


def _clean_markdown_links(content: str) -> str:
    """깨진 마크다운 링크를 텍스트만 남긴다."""
    # [텍스트]({{< ref ... >}}) → 텍스트 (Hugo ref 링크)
    content = re.sub(r"\[([^\]]+)\]\(\{\{.*?\}\}\)", r"\1", content)
    return content


def _normalize_whitespace(content: str) -> str:
    """연속된 빈 줄을 최대 2줄로 정리한다."""
    return re.sub(r"\n{3,}", "\n\n", content)


def _clean_content(content: str) -> str:
    """모든 정리 함수를 순서대로 적용한다."""
    content = _clean_frontmatter(content)
    content = _clean_hugo_tags(content)
    content = _clean_html(content)
    content = _clean_markdown_links(content)
    content = _normalize_whitespace(content)
    return content.strip()


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

    documents = []
    for doc in raw_docs:
        cleaned_content = _clean_content(doc.page_content)

        # 너무 짧은 문서는 스킵 (목차만 있는 _index.md 등)
        if len(cleaned_content) < MIN_DOC_LENGTH:
            continue

        title = _extract_title(cleaned_content)
        doc.page_content = cleaned_content
        doc.metadata["title"] = title or Path(doc.metadata.get("source", "")).stem

        documents.append(doc)

    return documents
