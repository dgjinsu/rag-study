"""
청크 텍스트 포맷팅 모듈.

CodeEntity를 임베딩에 적합한 텍스트로 변환한다.
포맷팅된 텍스트에는 패키지/클래스 컨텍스트, Javadoc, 소스 코드,
호출 관계 정보가 포함되어 검색 품질을 높인다.

포맷 구조 (메서드 예시):
    // Package: com.example.order.service
    // Class: OrderService (@Service)

    /** 주문을 생성한다. */
    @Transactional
    public OrderDto create(OrderRequest request) { ... }

    // Calls: OrderRepository.save, Validator.validate
    // Called by: OrderController.createOrder
"""

from __future__ import annotations

from src.models import CodeEntity


def format_chunk_text(
    entity: CodeEntity,
    part_source: str | None = None,
) -> str:
    """
    CodeEntity를 임베딩 대상 텍스트로 포맷팅한다.

    Args:
        entity: 원본 CodeEntity.
        part_source: 분할된 경우 해당 파트의 소스 코드. None이면 entity.source_code 전체 사용.

    Returns:
        포맷팅된 텍스트 문자열.
    """
    parts: list[str] = []

    # 1. 위치 헤더
    header = _format_location_header(entity)
    if header:
        parts.append(header)

    # 2. Javadoc
    if entity.javadoc:
        parts.append(entity.javadoc)

    # 3. 소스 코드
    source = part_source if part_source is not None else entity.source_code
    parts.append(source)

    # 4. 호출 관계 푸터
    footer = _format_call_graph_footer(entity)
    if footer:
        parts.append(footer)

    return "\n\n".join(parts)


def format_class_summary(
    entity: CodeEntity,
    all_entities: list[CodeEntity],
) -> str:
    """
    클래스/인터페이스/enum 엔티티를 요약 텍스트로 포맷팅한다.

    전체 소스 대신 필드 목록과 메서드 이름 목록을 포함하여
    클래스의 구조를 파악할 수 있게 한다.

    Args:
        entity: 클래스/인터페이스/enum CodeEntity.
        all_entities: 전체 엔티티 목록 (소속 멤버를 찾기 위해).

    Returns:
        포맷팅된 요약 텍스트.
    """
    parts: list[str] = []

    # 1. 위치 헤더
    header = _format_location_header(entity)
    if header:
        parts.append(header)

    # 2. Javadoc
    if entity.javadoc:
        parts.append(entity.javadoc)

    # 3. 클래스 선언문 + 멤버 요약
    summary = _build_class_summary(entity, all_entities)
    parts.append(summary)

    # 4. 호출 관계 푸터 (클래스 수준에서는 보통 없지만 있을 수도 있음)
    footer = _format_call_graph_footer(entity)
    if footer:
        parts.append(footer)

    return "\n\n".join(parts)


# ── 내부 헬퍼 함수 ──────────────────────────────────────────


def _format_location_header(entity: CodeEntity) -> str:
    """패키지와 클래스 위치를 주석 헤더로 포맷."""
    lines: list[str] = []

    if entity.package_name:
        lines.append(f"// Package: {entity.package_name}")

    if entity.class_name:
        # 클래스의 어노테이션을 찾아서 표시 (예: @Service)
        class_label = entity.class_name
        lines.append(f"// Class: {class_label}")

    return "\n".join(lines)


def _format_call_graph_footer(entity: CodeEntity) -> str:
    """calls/called_by를 주석으로 포맷."""
    lines: list[str] = []

    if entity.calls:
        calls_str = ", ".join(entity.calls)
        lines.append(f"// Calls: {calls_str}")

    if entity.called_by:
        called_by_str = ", ".join(entity.called_by)
        lines.append(f"// Called by: {called_by_str}")

    return "\n".join(lines)


def _build_class_summary(
    entity: CodeEntity,
    all_entities: list[CodeEntity],
) -> str:
    """클래스 선언문과 멤버 요약을 생성."""
    lines: list[str] = []

    # 어노테이션
    for ann in entity.annotations:
        lines.append(ann)

    # 클래스 선언 헤더 (예: "public class OrderService {")
    modifiers_str = " ".join(entity.modifiers)
    type_keyword = entity.entity_type  # "class", "interface", "enum"
    decl = f"{modifiers_str} {type_keyword} {entity.name}".strip()
    lines.append(f"{decl} {{")

    # 소속 멤버 찾기: 같은 클래스에 속하는 엔티티
    members = [
        e for e in all_entities
        if e.class_name == entity.name and e.qualified_name != entity.qualified_name
    ]

    # 필드 요약
    fields = [m for m in members if m.entity_type == "field"]
    if fields:
        lines.append("    // Fields:")
        for f in fields:
            type_str = f.return_type or "?"
            lines.append(f"    //   {type_str} {f.name}")

    # 메서드 요약
    methods = [m for m in members if m.entity_type in ("method", "constructor")]
    if methods:
        lines.append("    // Methods:")
        for m in methods:
            params = ", ".join(m.parameters) if m.parameters else ""
            ret = f" -> {m.return_type}" if m.return_type else ""
            lines.append(f"    //   {m.name}({params}){ret}")

    lines.append("}")

    return "\n".join(lines)
