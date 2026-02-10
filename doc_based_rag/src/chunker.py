"""문서 청킹 모듈.

마크다운 헤더 기반으로 1차 분할 후, 큰 섹션은 추가 분할한다.
각 청크에 헤더 계층 정보와 source 메타데이터가 포함된다.
"""

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src.config import settings

# 마크다운 헤더 레벨 정의
HEADERS_TO_SPLIT = [
    ("#", "header_1"),
    ("##", "header_2"),
    ("###", "header_3"),
]


def chunk_documents(documents: list[Document]) -> list[Document]:
    """문서 리스트를 청크로 분할한다.

    1단계: MarkdownHeaderTextSplitter로 헤더 기반 섹션 분리
    2단계: RecursiveCharacterTextSplitter로 큰 섹션 추가 분할

    Args:
        documents: 원본 Document 리스트.

    Returns:
        청크로 분할된 Document 리스트.
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

        # 1단계: 헤더 기반 분할
        header_chunks = md_splitter.split_text(doc.page_content)

        # 2단계: 큰 섹션 추가 분할
        final_chunks = text_splitter.split_documents(header_chunks)

        # 원본 메타데이터 병합
        for chunk in final_chunks:
            chunk.metadata["source"] = source
            chunk.metadata["title"] = title
            if chunk.page_content.strip():
                all_chunks.append(chunk)

    return all_chunks
