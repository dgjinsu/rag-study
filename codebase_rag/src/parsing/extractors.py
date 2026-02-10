"""
코드 엔티티 추출 모듈.

tree-sitter AST를 순회하여 Java 소스 코드에서 구조화된 CodeEntity 객체를 추출한다.
이 모듈은 파싱 파이프라인에서 가장 복잡한 핵심 모듈이다.

추출 대상:
- 클래스/인터페이스/enum 선언
- 메서드 선언 (파라미터, 반환타입, 어노테이션, Javadoc 포함)
- 생성자 선언
- 필드 선언 (타입 정보 포함, 호출 그래프 해석에 활용)
- 메서드 호출 관계 (method_invocation 노드)

AST 순회 흐름:
    root_node
    ├── package_declaration → 패키지명 추출
    └── class_declaration
        ├── 클래스 엔티티 생성
        └── class_body
            ├── method_declaration → 메서드 엔티티 생성
            ├── constructor_declaration → 생성자 엔티티 생성
            ├── field_declaration → 필드 엔티티 생성
            └── class_declaration (중첩 클래스) → 재귀 처리
"""

from pathlib import Path

from tree_sitter import Node, Tree

from src.models import CodeEntity
from src.parsing.comment_extractor import (
    extract_annotations,
    extract_javadoc,
    extract_modifiers,
)


class EntityExtractor:
    """
    tree-sitter AST에서 CodeEntity 객체를 추출하는 추출기.

    하나의 Java 파일을 입력받아 해당 파일에 정의된 모든 클래스, 메서드,
    생성자, 필드를 CodeEntity 리스트로 반환한다.

    추출 과정:
    1. 패키지 선언 추출 (qualified_name 구성에 필요)
    2. 루트 노드부터 재귀적으로 선언문 탐색
    3. 각 선언에서 이름, 어노테이션, 수정자, Javadoc, 호출 관계 추출
    """

    def extract(self, tree: Tree, source: bytes, file_path: Path) -> list[CodeEntity]:
        """
        AST에서 모든 코드 엔티티를 추출한다.

        Args:
            tree: tree-sitter 파싱 결과 AST
            source: 원본 소스 바이트 (노드 텍스트 추출에 사용)
            file_path: Java 파일 경로 (메타데이터용)

        Returns:
            추출된 CodeEntity 리스트
        """
        entities = []
        # 1단계: 패키지명 추출 (예: "com.mirero.pwm.recipe.domain")
        package_name = self._extract_package(tree.root_node, source)
        # 2단계: 모든 선언문을 재귀 순회하며 엔티티 추출
        self._walk_declarations(tree.root_node, source, file_path, package_name, None, entities)
        return entities

    def _extract_package(self, root: Node, source: bytes) -> str | None:
        """
        루트 노드에서 package 선언을 찾아 패키지명을 반환한다.

        Java AST 구조:
            program
            └── package_declaration
                └── scoped_identifier ("com.example.service")
                    또는 identifier ("util")

        Returns:
            패키지명 문자열 또는 None (패키지 미선언 시)
        """
        for child in root.children:
            if child.type == "package_declaration":
                for sub in child.children:
                    if sub.type == "scoped_identifier" or sub.type == "identifier":
                        return source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
        return None

    def _walk_declarations(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
        package_name: str | None,
        enclosing_class: str | None,
        entities: list[CodeEntity],
    ):
        """
        AST 노드를 순회하며 클래스/인터페이스/enum 선언을 탐색한다.

        최상위 수준에서 시작하여, class_body 내부의 중첩 선언도 재귀적으로 처리한다.
        enclosing_class는 현재 노드가 속한 클래스명으로, 중첩 클래스 처리에 사용된다.
        """
        for child in node.children:
            if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                self._extract_class_like(child, source, file_path, package_name, enclosing_class, entities)
            elif child.type == "class_body":
                # class_body 노드 내부를 재귀 탐색 (중첩 클래스 등)
                self._walk_declarations(child, source, file_path, package_name, enclosing_class, entities)

    def _extract_class_like(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
        package_name: str | None,
        enclosing_class: str | None,
        entities: list[CodeEntity],
    ):
        """
        클래스/인터페이스/enum 선언에서 엔티티를 추출하고, 멤버도 재귀 추출한다.

        처리 단계:
        1. 선언문 자체를 CodeEntity로 생성 (클래스 수준)
        2. class_body 내의 멤버를 순회하며 메서드/생성자/필드 추출
        3. 중첩 클래스가 있으면 재귀적으로 다시 이 함수를 호출

        Args:
            node: class_declaration/interface_declaration/enum_declaration 노드
            enclosing_class: 이 클래스를 감싸는 외부 클래스명 (최상위이면 None)
        """
        # 노드 타입을 entity_type 문자열로 매핑
        entity_type_map = {
            "class_declaration": "class",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
        }
        entity_type = entity_type_map[node.type]
        name = self._get_name(node, source)
        if not name:
            return

        # qualified_name 구성: 패키지.클래스.이름
        qualified = self._qualify(package_name, enclosing_class, name)
        # 어노테이션, 수정자, Javadoc 추출
        annotations = extract_annotations(node, source)
        modifiers = extract_modifiers(node, source)
        javadoc = extract_javadoc(node, source)

        # 클래스/인터페이스/enum 엔티티 생성
        entities.append(CodeEntity(
            entity_type=entity_type,
            name=name,
            qualified_name=qualified,
            file_path=str(file_path),
            # node.start_point => (row, column) 반환
            start_line=node.start_point[0] + 1,   # tree-sitter는 0-based → 1-based로 변환
            end_line=node.end_point[0] + 1,
            source_code=source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            class_name=enclosing_class,
            package_name=package_name,
            modifiers=modifiers,
            annotations=annotations,
            javadoc=javadoc,
        ))

        # 클래스 본문 내의 멤버 추출 (메서드, 생성자, 필드, 중첩 클래스)
        body = node.child_by_field_name("body")
        if body:
            for member in body.children:
                if member.type == "method_declaration":
                    self._extract_method(member, source, file_path, package_name, name, entities)
                elif member.type == "constructor_declaration":
                    self._extract_constructor(member, source, file_path, package_name, name, entities)
                elif member.type == "field_declaration":
                    self._extract_field(member, source, file_path, package_name, name, entities)
                elif member.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                    # 중첩 클래스: 현재 클래스명을 enclosing_class로 전달
                    self._extract_class_like(member, source, file_path, package_name, name, entities)

    def _extract_method(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
        package_name: str | None,
        class_name: str,
        entities: list[CodeEntity],
    ):
        """
        메서드 선언에서 엔티티를 추출한다.

        추출 항목: 이름, qualified_name, 파라미터, 반환타입,
        어노테이션, 수정자, Javadoc, 호출 목록(calls)

        호출 목록은 메서드 본문의 method_invocation 노드에서 추출되며,
        나중에 CallGraph.resolve_invocations()에서 정규화된다.
        """
        name = self._get_name(node, source)
        if not name:
            return

        qualified = self._qualify(package_name, class_name, name)
        annotations = extract_annotations(node, source)
        modifiers = extract_modifiers(node, source)
        javadoc = extract_javadoc(node, source)
        parameters = self._extract_parameters(node, source)
        return_type = self._extract_return_type(node, source)
        # 메서드 본문 내의 모든 메서드 호출을 추출 (아직 미해석 상태)
        calls = self._extract_method_invocations(node, source)

        entities.append(CodeEntity(
            entity_type="method",
            name=name,
            qualified_name=qualified,
            file_path=str(file_path),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            class_name=class_name,
            package_name=package_name,
            modifiers=modifiers,
            parameters=parameters,
            return_type=return_type,
            annotations=annotations,
            javadoc=javadoc,
            calls=calls,
        ))

    def _extract_constructor(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
        package_name: str | None,
        class_name: str,
        entities: list[CodeEntity],
    ):
        """
        생성자 선언에서 엔티티를 추출한다.

        메서드와 동일한 정보를 추출하되, entity_type이 "constructor"이고
        return_type이 없다는 점이 다르다.
        """
        name = self._get_name(node, source)
        if not name:
            return

        qualified = self._qualify(package_name, class_name, name)
        annotations = extract_annotations(node, source)
        modifiers = extract_modifiers(node, source)
        javadoc = extract_javadoc(node, source)
        parameters = self._extract_parameters(node, source)
        calls = self._extract_method_invocations(node, source)

        entities.append(CodeEntity(
            entity_type="constructor",
            name=name,
            qualified_name=qualified,
            file_path=str(file_path),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            class_name=class_name,
            package_name=package_name,
            modifiers=modifiers,
            parameters=parameters,
            annotations=annotations,
            javadoc=javadoc,
            calls=calls,
        ))

    def _extract_field(
        self,
        node: Node,
        source: bytes,
        file_path: Path,
        package_name: str | None,
        class_name: str,
        entities: list[CodeEntity],
    ):
        """
        필드 선언에서 엔티티를 추출한다.

        Java AST 구조:
            field_declaration
            ├── modifiers (public, private 등)
            ├── type (필드 타입, 예: OrderService)
            └── variable_declarator
                └── name (identifier, 필드명)

        필드의 타입 정보(return_type에 저장)는 호출 그래프 해석 시
        "필드명.메서드()" 호출을 "필드타입.메서드()"로 매핑하는 데 핵심적으로 사용된다.
        (예: orderService.create() → OrderService.create())
        """
        # variable_declarator에서 필드명 추출
        declarator = self._find_child(node, "variable_declarator")
        if not declarator:
            return
        name_node = declarator.child_by_field_name("name")
        if not name_node:
            return

        name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        qualified = self._qualify(package_name, class_name, name)
        annotations = extract_annotations(node, source)
        modifiers = extract_modifiers(node, source)
        # 필드 타입 추출 (Spring DI에서 주입되는 의존성 타입 파악에 중요)
        field_type = self._extract_field_type(node, source)

        entities.append(CodeEntity(
            entity_type="field",
            name=name,
            qualified_name=qualified,
            file_path=str(file_path),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source_code=source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
            class_name=class_name,
            package_name=package_name,
            modifiers=modifiers,
            annotations=annotations,
            return_type=field_type,  # 필드 타입을 return_type에 저장
        ))

    def _extract_parameters(self, node: Node, source: bytes) -> list[str]:
        """
        메서드/생성자의 파라미터 목록을 추출한다.

        각 파라미터는 "타입 이름" 형태의 문자열로 반환된다.
        가변 인수(varargs)도 spread_parameter로 처리된다.

        Returns:
            파라미터 문자열 리스트 (예: ["OrderRequest request", "Long id"])
        """
        params = []
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return params
        for child in params_node.children:
            # formal_parameter: 일반 파라미터
            # spread_parameter: 가변 인수 (String... args)
            if child.type == "formal_parameter" or child.type == "spread_parameter":
                text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                params.append(text)
        return params

    def _extract_return_type(self, node: Node, source: bytes) -> str | None:
        """
        메서드의 반환 타입을 추출한다.

        tree-sitter에서 반환 타입은 method_declaration의 type 필드이다.
        void, String, List<OrderDto> 등의 타입 문자열을 반환한다.
        """
        type_node = node.child_by_field_name("type")
        if type_node:
            return source[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace")
        return None

    def _extract_field_type(self, node: Node, source: bytes) -> str | None:
        """
        필드의 타입을 추출한다.

        field_declaration의 type 필드에서 추출한다.
        제네릭 타입(List<String> 등)도 전체 문자열로 반환되지만,
        extract_field_types()에서 <이전 부분만 사용한다.
        """
        type_node = node.child_by_field_name("type")
        if type_node:
            return source[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace")
        return None

    def _extract_method_invocations(self, node: Node, source: bytes) -> list[str]:
        """
        메서드 본문에서 모든 메서드 호출(method_invocation)을 추출한다.

        재귀적으로 AST를 순회하며 method_invocation 노드를 수집한다.
        중복 호출은 seen 집합으로 제거한다.

        Returns:
            호출 문자열 리스트 (예: ["orderService.create", "validate", "log.info"])
        """
        calls = []
        seen = set()
        self._collect_invocations(node, source, calls, seen)
        return calls

    def _collect_invocations(self, node: Node, source: bytes, calls: list[str], seen: set[str]):
        """
        재귀적으로 method_invocation 노드를 수집하는 내부 함수.

        method_invocation AST 구조:
            method_invocation
            ├── object (호출 대상, 예: orderService)
            ├── name (메서드명, 예: create)
            └── arguments (인수 목록)

        체이닝 호출 처리:
            a.b().c().d() 같은 체이닝에서 object는 "a.b().c()"가 되므로
            마지막 식별자만 추출하여 "c.d"로 단순화한다.
        """
        if node.type == "method_invocation":
            name_node = node.child_by_field_name("name")
            object_node = node.child_by_field_name("object")
            if name_node:
                method_name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                if object_node:
                    obj_text = source[object_node.start_byte:object_node.end_byte].decode("utf-8", errors="replace")
                    # 체이닝 호출 단순화: "a.b.c" → "c" (마지막 식별자만 사용)
                    if "." in obj_text:
                        parts = obj_text.split(".")
                        obj_text = parts[-1]
                    call_str = f"{obj_text}.{method_name}"
                else:
                    # 객체 없이 호출 = 같은 클래스 내 메서드 호출
                    call_str = method_name
                # 중복 제거
                if call_str not in seen:
                    seen.add(call_str)
                    calls.append(call_str)

        # 모든 자식 노드를 재귀 탐색
        for child in node.children:
            self._collect_invocations(child, source, calls, seen)

    def _get_name(self, node: Node, source: bytes) -> str | None:
        """노드의 name 필드에서 식별자를 추출한다."""
        name_node = node.child_by_field_name("name")
        if name_node:
            return source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        return None

    def _qualify(self, package: str | None, class_name: str | None, name: str) -> str:
        """
        패키지명, 클래스명, 이름을 조합하여 정규화된 이름을 생성한다.

        예: ("com.example", "OrderService", "create")
            → "com.example.OrderService.create"
        """
        parts = [p for p in (package, class_name, name) if p]
        return ".".join(parts)

    def _find_child(self, node: Node, child_type: str) -> Node | None:
        """특정 타입의 자식 노드를 찾아 반환한다."""
        for child in node.children:
            if child.type == child_type:
                return child
        return None


def extract_field_types(entities: list[CodeEntity]) -> dict[str, dict[str, str]]:
    """
    클래스별 필드 타입 맵을 구축한다.

    호출 그래프 해석에서 "필드명.메서드()" 형태의 호출을
    "필드타입.메서드()"로 변환하는 데 사용된다.

    예를 들어, OrderService 클래스에 다음 필드가 있으면:
        private final OrderRepository orderRepository;

    결과 맵: {"OrderService": {"orderRepository": "OrderRepository"}}

    이 맵을 통해 orderRepository.save() → OrderRepository.save()로 해석한다.

    제네릭 타입은 <이전의 기본 타입만 사용한다:
        List<OrderDto> → "List" (제네릭 인수 제거)

    Returns:
        {클래스명: {필드명: 필드타입}} 형태의 중첩 딕셔너리
    """
    field_types: dict[str, dict[str, str]] = {}
    for entity in entities:
        if entity.entity_type == "field" and entity.class_name and entity.return_type:
            if entity.class_name not in field_types:
                field_types[entity.class_name] = {}
            # 제네릭 타입에서 기본 타입만 추출 (List<String> → List)
            type_name = entity.return_type
            if "<" in type_name:
                type_name = type_name[:type_name.index("<")]
            field_types[entity.class_name][entity.name] = type_name
    return field_types
