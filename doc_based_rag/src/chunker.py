"""문서 청킹 모듈.

마크다운 헤더 기반으로 1차 분할 후, 큰 섹션은 추가 분할한다.
각 청크에 헤더 계층 정보와 source 메타데이터가 포함된다.
청크 본문 앞에 문맥 정보(제목 + 헤더 경로)를 주입한다.
코드 블록 안의 #은 헤더로 오인되지 않도록 보호한다.
"""

import re

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src.config import settings

HEADERS_TO_SPLIT = [
    ("#", "header_1"),
    ("##", "header_2"),
    ("###", "header_3"),
]

# 코드 블록 안의 #을 임시로 치환할 문자열
_HASH_PLACEHOLDER = "§HASH§"


def _protect_code_blocks(text: str) -> str:
    """코드 블록(``` ... ```) 안의 #을 플레이스홀더로 치환한다.

    MarkdownHeaderTextSplitter가 코드 블록 안의 # 주석을
    헤더로 오인하는 것을 방지한다.
    """
    def _replace_hash(match: re.Match) -> str:
        return match.group(0).replace("#", _HASH_PLACEHOLDER)

    return re.sub(r"```.*?```", _replace_hash, text, flags=re.DOTALL)


def _restore_code_blocks(text: str) -> str:
    """플레이스홀더를 원래 #으로 복원한다."""
    return text.replace(_HASH_PLACEHOLDER, "#")


def _build_context_prefix(title: str, metadata: dict) -> str:
    """청크의 문맥 정보를 문자열로 만든다.

    예: "[Kubelet 인증/인가 > Kubelet 인증 > 개요]"
    """
    parts = []
    if title:
        parts.append(title)
    for key in ("header_1", "header_2", "header_3"):
        value = metadata.get(key, "")
        if value and value != title:
            parts.append(value)

    if not parts:
        return ""
    return "[" + " > ".join(parts) + "]\n"


def chunk_documents(documents: list[Document]) -> list[Document]:
    """문서 리스트를 청크로 분할한다.

    1단계: 코드 블록 안의 # 보호
    2단계: MarkdownHeaderTextSplitter로 헤더 기반 섹션 분리
    3단계: RecursiveCharacterTextSplitter로 큰 섹션 추가 분할
    4단계: # 복원 + 문맥 접두사 주입
    """
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT,
        strip_headers=False,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks: list[Document] = []

    for doc in documents:
        source = doc.metadata.get("source", "")
        title = doc.metadata.get("title", "")

        # 1단계: 코드 블록 안의 # 보호
        protected_text = _protect_code_blocks(doc.page_content)

        # 2단계: 헤더 기반 분할 (보호된 텍스트로)
        header_chunks = md_splitter.split_text(protected_text)

        # 3단계: 큰 섹션 추가 분할
        final_chunks = text_splitter.split_documents(header_chunks)

        # 4단계: # 복원 + 문맥 접두사 주입 + 메타데이터 병합
        for chunk in final_chunks:
            chunk.metadata["source"] = source
            chunk.metadata["title"] = title

            # 플레이스홀더를 원래 #으로 복원
            content = _restore_code_blocks(chunk.page_content).strip()
            if not content:
                continue

            prefix = _build_context_prefix(title, chunk.metadata)
            chunk.page_content = prefix + content
            all_chunks.append(chunk)

    return all_chunks
