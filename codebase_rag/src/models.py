"""
데이터 모델 모듈.

tree-sitter AST에서 추출된 코드 요소를 표현하는 모델을 정의한다.

데이터 흐름:
    Java 소스 →[파싱]→ CodeEntity
"""

from __future__ import annotations

from typing import Literal # 허용되는 값 제한

from pydantic import BaseModel # 데이터 검증 라이브러리


class CodeEntity(BaseModel):
    """
    tree-sitter AST에서 추출된 하나의 코드 요소.

    EntityExtractor가 Java AST를 순회하면서 생성한다.
    클래스, 메서드, 생성자, 필드, enum, interface 중 하나를 나타낸다.
    """

    # 필수 필드
    entity_type: Literal["class", "method", "constructor", "field", "enum", "interface"]
    name: str                          # 단순 이름 (예: "processOrder")
    qualified_name: str                # 정규화된 이름 (예: "com.example.OrderService.processOrder")
    file_path: str                     # 원본 Java 파일의 절대 경로
    start_line: int                    # 소스 코드 시작 라인 (1-based)
    end_line: int                      # 소스 코드 끝 라인 (1-based)
    source_code: str                   # 원본 Java 소스 코드 전문

    # 선택 필드
    class_name: str | None = None      # 소속 클래스명 (최상위이면 None)
    package_name: str | None = None    # Java 패키지명
    modifiers: list[str] = []          # 수정자 목록 (public, static, final 등)
    parameters: list[str] = []         # 파라미터 목록 (예: ["OrderRequest request"])
    return_type: str | None = None     # 반환 타입 (메서드) 또는 필드 타입 (필드)
    annotations: list[str] = []        # 어노테이션 목록 (예: ["@Service", "@Override"])
    javadoc: str | None = None         # Javadoc 주석 전문 (/** ... */)
    calls: list[str] = []              # 이 메서드가 호출하는 메서드 목록 (해석 전/후)
    called_by: list[str] = []          # 이 메서드를 호출하는 메서드 목록 (해석 후에만)


class Chunk(BaseModel):
    """
    RAG 검색의 기본 단위.

    하나의 CodeEntity(또는 긴 메서드를 분할한 일부분)에 대응된다.
    chunk_text는 임베딩에 사용되는 포맷팅된 텍스트이고,
    메타데이터는 ChromaDB 저장 및 필터링에 사용된다.
    """

    # 식별
    chunk_id: str                      # "{qualified_name}#{part_index}" — upsert용 결정론적 ID
    source_entity_id: str              # 원본 CodeEntity의 qualified_name

    # 텍스트
    chunk_text: str                    # 임베딩 대상 포맷팅 텍스트
    source_code: str                   # 원본 소스 코드

    # 위치
    file_path: str
    start_line: int
    end_line: int

    # 분류
    entity_type: Literal["class", "method", "constructor", "field", "enum", "interface"]
    name: str
    qualified_name: str

    # 컨텍스트 메타데이터
    class_name: str | None = None
    package_name: str | None = None
    modifiers: list[str] = []
    parameters: list[str] = []
    return_type: str | None = None
    annotations: list[str] = []
    javadoc: str | None = None

    # 호출 그래프
    calls: list[str] = []
    called_by: list[str] = []

    # 청킹 메타데이터
    part_index: int = 0                # 분할 시 파트 번호 (0-based)
    total_parts: int = 1               # 총 파트 수
