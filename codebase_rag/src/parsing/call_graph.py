"""
호출 그래프(Call Graph) 모듈.

메서드 간의 호출 관계를 방향 그래프로 구축하고 관리한다.
노드는 메서드의 qualified_name, 엣지는 호출 관계(caller→callee)이다.

호출 해석 전략 (우선순위):
1. 직접 매칭: "ClassName.methodName"이 method_map에 유일하게 존재하면 사용
2. 필드 타입 해석: "fieldName.method"에서 필드 타입을 찾아 "FieldType.method"로 변환
   (Spring DI로 주입된 의존성 호출을 해석하는 핵심 전략)
3. 같은 클래스 호출: 객체 없이 "method()"만 있으면 현재 클래스에서 탐색
4. 미해석: 위 전략으로 해석 불가하면 "?.methodName"으로 표시

사용 예:
    graph = CallGraph()
    graph.resolve_invocations(all_entities)
    chain = graph.get_call_chain("com.example.Service.process", depth=3)
"""

from collections import defaultdict

from src.models import CodeEntity
from src.parsing.extractors import extract_field_types


class CallGraph:
    """
    메서드 호출 관계를 나타내는 방향 그래프.

    양방향 엣지를 관리한다:
    - edges: caller → {callee1, callee2, ...}  (순방향: 이 메서드가 호출하는 것들)
    - reverse_edges: callee → {caller1, caller2, ...}  (역방향: 이 메서드를 호출하는 것들)
    """

    def __init__(self):
        # caller → callees 매핑 (순방향 그래프)
        self.edges: dict[str, set[str]] = defaultdict(set)
        # callee → callers 매핑 (역방향 그래프, called_by 구성에 사용)
        self.reverse_edges: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, caller: str, callee: str):
        """caller→callee 엣지를 양방향으로 추가한다."""
        self.edges[caller].add(callee)
        self.reverse_edges[callee].add(caller)

    def get_callees(self, method: str) -> set[str]:
        """주어진 메서드가 호출하는 모든 메서드를 반환한다."""
        return self.edges.get(method, set())

    def get_callers(self, method: str) -> set[str]:
        """주어진 메서드를 호출하는 모든 메서드를 반환한다."""
        return self.reverse_edges.get(method, set())

    def get_call_chain(self, method: str, depth: int = 3, direction: str = "forward") -> list[str]:
        """
        BFS(너비 우선 탐색)로 호출 체인을 추적한다.

        특정 메서드에서 시작하여 depth 깊이까지 호출 관계를 따라간다.
        비즈니스 플로우 추적에 유용하다.
        예: "RecipeUseCase.create()" → depth=3으로 생성 플로우 전체 파악

        Args:
            method: 탐색 시작점의 qualified_name
            depth: 최대 탐색 깊이 (기본 3)
            direction: "forward"=호출하는 메서드 추적, "backward"=호출당하는 메서드 추적

        Returns:
            발견된 메서드들의 qualified_name 리스트 (시작점 제외)
        """
        visited = set()
        result = []
        queue = [(method, 0)]  # (메서드명, 현재 깊이)
        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            # 시작점은 결과에 포함하지 않음
            if current != method:
                result.append(current)
            # 방향에 따라 이웃 노드 선택
            neighbors = self.get_callees(current) if direction == "forward" else self.get_callers(current)
            for neighbor in neighbors:
                if neighbor not in visited:
                    queue.append((neighbor, d + 1))
        return result

    def resolve_invocations(self, entities: list[CodeEntity]):
        """
        모든 엔티티의 미해석 호출(raw calls)을 정규화된 qualified_name으로 해석한다.

        처리 흐름:
        1. method_map 구축: 메서드명 → [qualified_name 리스트]
        2. field_types 구축: 클래스명 → {필드명: 필드타입}
        3. 각 메서드의 calls 목록에서 raw_call을 해석하여 그래프 엣지 생성
        4. 역방향 엣지를 사용하여 모든 메서드의 called_by 리스트 갱신

        호출 후 변화:
        - entity.calls: ["orderService.create", "validate"]
          → ["com.example.OrderService.create", "com.example.ThisClass.validate"]
        - entity.called_by: [] → ["com.example.Controller.handleRequest"]
        - self.edges/reverse_edges: 그래프 엣지 구축 완료

        Args:
            entities: 파싱된 모든 CodeEntity 리스트
        """
        # 1. 메서드명 → qualified_name 매핑 구축
        method_map = self._build_method_map(entities)
        # 2. 클래스별 필드 타입 맵 구축 (Spring DI 필드 해석용)
        field_types = extract_field_types(entities)

        # 3. 각 메서드/생성자의 호출 목록을 해석하고 그래프 엣지 추가
        for entity in entities:
            if entity.entity_type not in ("method", "constructor"):
                continue
            if not entity.calls:
                continue

            resolved_calls = []
            for raw_call in entity.calls:
                resolved = self._resolve_call(
                    raw_call, entity.class_name, method_map, field_types
                )
                resolved_calls.append(resolved)
                # 그래프에 엣지 추가: 현재 메서드 → 해석된 호출 대상
                self.add_edge(entity.qualified_name, resolved)

            # 해석된 호출 목록으로 갱신
            entity.calls = resolved_calls

        # 4. 역방향 엣지를 사용하여 called_by 리스트 채우기
        for entity in entities:
            if entity.entity_type not in ("method", "constructor"):
                continue
            callers = self.get_callers(entity.qualified_name)
            entity.called_by = list(callers)

    def _build_method_map(self, entities: list[CodeEntity]) -> dict[str, list[str]]:
        """
        메서드명 → qualified_name 리스트 매핑을 구축한다.

        두 가지 키로 인덱싱:
        - 단순 메서드명: "create" → ["com.a.Service.create", "com.b.Other.create"]
        - 클래스.메서드명: "Service.create" → ["com.a.Service.create"]

        후자가 더 정확한 해석을 가능하게 한다.
        """
        method_map: dict[str, list[str]] = defaultdict(list)
        for entity in entities:
            if entity.entity_type in ("method", "constructor"):
                # 단순 메서드명으로 인덱싱
                method_map[entity.name].append(entity.qualified_name)
                # ClassName.methodName 형태로도 인덱싱
                if entity.class_name:
                    key = f"{entity.class_name}.{entity.name}"
                    method_map[key].append(entity.qualified_name)
        return method_map

    def _resolve_call(
        self,
        raw_call: str,
        current_class: str | None,
        method_map: dict[str, list[str]],
        field_types: dict[str, dict[str, str]],
    ) -> str:
        """
        하나의 raw 호출을 qualified_name으로 해석한다.

        해석 전략 (우선순위순):

        [객체.메서드() 형태인 경우]
        1) "ClassName.method" 직접 매칭 → method_map에 유일하면 확정
        2) 필드 타입 해석 → 현재 클래스의 필드명과 대조하여 타입 결정
        3) 메서드명만으로 전체 탐색 → 유일하면 확정
        4) 해석 실패 → "?.obj.method" 반환

        [메서드() 형태인 경우 (같은 클래스 내 호출)]
        1) "CurrentClass.method"로 method_map 검색
        2) 전체 검색 → 유일하면 확정
        3) 해석 실패 → "?.method" 반환

        Args:
            raw_call: 미해석 호출 문자열 (예: "orderService.create" 또는 "validate")
            current_class: 호출이 발생한 클래스명
            method_map: 메서드명→qualified_name 매핑
            field_types: 클래스별 필드 타입 맵

        Returns:
            해석된 qualified_name 또는 "?.호출명" (미해석)
        """

        if "." in raw_call:
            obj_name, method_name = raw_call.rsplit(".", 1)

            # 전략 1: ClassName.methodName 직접 매칭
            candidates = method_map.get(raw_call, [])
            if len(candidates) == 1:
                return candidates[0]

            # 전략 2: 필드 타입 기반 해석
            # 예: orderService.create() → OrderService 타입 필드 → OrderService.create
            if current_class and current_class in field_types:
                field_type = field_types[current_class].get(obj_name)
                if field_type:
                    type_key = f"{field_type}.{method_name}"
                    candidates = method_map.get(type_key, [])
                    if len(candidates) == 1:
                        return candidates[0]
                    if candidates:
                        return candidates[0]  # 여러 후보 중 첫 번째 선택

            # 전략 3: 메서드명만으로 전체 탐색
            candidates = method_map.get(method_name, [])
            if len(candidates) == 1:
                return candidates[0]

            # 해석 실패
            return f"?.{raw_call}"
        else:
            # 객체 없이 호출 = 같은 클래스 내 메서드 호출
            if current_class:
                key = f"{current_class}.{raw_call}"
                candidates = method_map.get(key, [])
                if candidates:
                    return candidates[0]

            # 전체 탐색
            candidates = method_map.get(raw_call, [])
            if len(candidates) == 1:
                return candidates[0]

            # 해석 실패
            return f"?.{raw_call}"
