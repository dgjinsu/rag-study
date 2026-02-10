"""
주석 및 어노테이션 추출 모듈.

tree-sitter AST 노드에서 다음 요소를 추출하는 헬퍼 함수들:
- Javadoc 주석 (/** ... */)
- 인라인 주석 (// ...)
- 어노테이션 (@Service, @Override 등)
- 수정자 키워드 (public, static, final 등)

이 모듈의 함수들은 extractors.py에서 엔티티 추출 시 호출된다.

tree-sitter AST 구조 (Java):
    class_declaration
    ├── modifiers
    │   ├── marker_annotation (@Service처럼 인수 없는 어노테이션)
    │   ├── annotation (@Value("...")처럼 인수 있는 어노테이션)
    │   └── "public", "static" 등의 키워드 노드
    ├── name (identifier)
    └── body (class_body)
"""

from tree_sitter import Node


def extract_javadoc(node: Node, source: bytes) -> str | None:
    """
    선언 노드 바로 앞에 위치한 Javadoc 주석을 추출한다.

    tree-sitter에서 Javadoc(/** ... */)은 block_comment 노드로 파싱된다.
    prev_named_sibling을 통해 선언문 바로 직전의 형제 노드를 확인하여
    Javadoc 여부를 판별한다.

    Args:
        node: 메서드/클래스/필드 등의 선언 노드
        source: 원본 소스 바이트

    Returns:
        Javadoc 문자열 (/** ... */) 또는 None
    """
    # 현재 노드의 바로 이전 형제 노드를 가져온다
    prev = node.prev_named_sibling
    if prev is None:
        return None

    # 이전 형제가 block_comment이고 /**로 시작하면 Javadoc
    # 일반 블록 주석(/* ... */)은 제외된다
    if prev.type == "block_comment":
        text = source[prev.start_byte:prev.end_byte].decode("utf-8", errors="replace")
        if text.startswith("/**"):
            return text
    return None


def extract_inline_comments(node: Node, source: bytes) -> list[str]:
    """
    노드 범위 내의 모든 라인 주석(// ...)을 추출한다.

    재귀적으로 자식 노드를 순회하며 line_comment 타입을 수집한다.
    메서드 본문 내의 주석을 청크 메타데이터로 활용할 때 사용된다.

    Args:
        node: 탐색 시작 노드 (보통 메서드 본문)
        source: 원본 소스 바이트

    Returns:
        라인 주석 문자열 리스트 (// 포함)
    """
    comments = []
    _collect_comments(node, source, comments)
    return comments


def _collect_comments(node: Node, source: bytes, results: list[str]):
    """
    재귀적으로 AST를 순회하며 line_comment 노드를 수집하는 내부 함수.

    tree-sitter에서 line_comment은 //로 시작하는 한 줄 주석이다.
    DFS(깊이 우선 탐색)로 모든 자식을 순회하므로 중첩된 블록 내의
    주석도 빠짐없이 수집된다.
    """
    if node.type == "line_comment":
        text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        results.append(text)
    for child in node.children:
        _collect_comments(child, source, results)


def extract_annotations(node: Node, source: bytes) -> list[str]:
    """
    선언 노드의 modifiers에서 어노테이션 이름을 추출한다.

    Java 선언문의 어노테이션은 modifiers 노드의 자식으로 파싱된다:
    - marker_annotation: 인수 없음 (예: @Override, @Service)
    - annotation: 인수 있음 (예: @Value("test"), @RequestMapping(path="/api"))

    두 경우 모두 name 필드에서 어노테이션 이름을 추출하고 @를 붙인다.
    이 정보는 패턴 추론(Service, Controller 등)에 활용된다.

    Args:
        node: 클래스/메서드/필드 선언 노드
        source: 원본 소스 바이트

    Returns:
        어노테이션 이름 리스트 (예: ["@Service", "@Override", "@Transactional"])
    """
    annotations = []
    for child in node.children:
        if child.type == "modifiers":
            for mod_child in child.children:
                if mod_child.type in ("marker_annotation", "annotation"):
                    # 어노테이션의 name 필드에서 이름 추출
                    name_node = mod_child.child_by_field_name("name")
                    if name_node:
                        annotations.append(
                            "@" + source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                        )
    return annotations


def extract_modifiers(node: Node, source: bytes) -> list[str]:
    """
    선언 노드의 modifiers에서 수정자 키워드를 추출한다.

    어노테이션을 제외한 순수 수정자만 반환한다:
    public, private, protected, static, final, abstract, synchronized 등

    수정자 정보는 엔티티의 접근 수준과 특성을 파악하는 데 사용된다.

    Args:
        node: 클래스/메서드/필드 선언 노드
        source: 원본 소스 바이트

    Returns:
        수정자 키워드 리스트 (예: ["public", "static", "final"])
    """
    modifiers = []
    for child in node.children:
        if child.type == "modifiers":
            for mod_child in child.children:
                # 어노테이션이 아닌 자식만 수정자로 간주
                if mod_child.type not in ("marker_annotation", "annotation"):
                    text = source[mod_child.start_byte:mod_child.end_byte].decode("utf-8", errors="replace")
                    modifiers.append(text)
    return modifiers
