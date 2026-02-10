# AST 파싱 & 엔티티 추출 — 단계별 추적

이 문서는 하나의 Java 파일이 `CodeEntity` 리스트로 변환되는 **전체 과정**을 따라간다.
실제 코드와 AST를 대조하며, 각 단계에서 **무엇을 보고 무엇을 꺼내는지** 정확히 보여준다.

---

## 예시 Java 파일

이 파일을 처음부터 끝까지 추적한다:

```java
package com.example.order;

/** 주문 처리 서비스 */
@Service
public class OrderService {

    private final OrderRepository orderRepo;

    @Autowired
    public OrderService(OrderRepository orderRepo) {
        this.orderRepo = orderRepo;
    }

    /**
     * 주문을 생성한다.
     * @param req 주문 요청
     */
    @Transactional
    public OrderDto create(OrderRequest req) {
        validate(req);
        Order order = orderRepo.save(req.toEntity());
        return OrderDto.from(order);
    }

    private void validate(OrderRequest req) {
        if (req.getAmount() <= 0) {
            throw new IllegalArgumentException("금액 오류");
        }
    }
}
```

---

## 전체 흐름 한눈에 보기

```
              Java 파일 (텍스트)
                     │
   ┌─────────────────┼─────────────────┐
   │           1. JavaParser            │
   │         (java_parser.py)           │
   │                                    │
   │   파일 → bytes → tree-sitter      │
   │   → AST 트리 생성                  │
   └─────────────────┼─────────────────┘
                     │
                     ▼
              AST (Node 트리)
                     │
   ┌─────────────────┼─────────────────┐
   │         2. EntityExtractor         │
   │          (extractors.py)           │
   │                                    │
   │   AST 트리를 위→아래 순회하며      │
   │   선언문마다 CodeEntity 생성       │
   │                                    │
   │   내부에서 comment_extractor.py    │
   │   함수들을 호출하여 Javadoc,       │
   │   어노테이션, 수정자 추출          │
   └─────────────────┼─────────────────┘
                     │
                     ▼
           CodeEntity 리스트 (6개)
                     │
   ┌─────────────────┼─────────────────┐
   │           3. CallGraph             │
   │          (call_graph.py)           │
   │                                    │
   │   "orderRepo.save" 같은 미해석     │
   │   호출을 "OrderRepository.save"    │
   │   로 변환. calls/called_by 갱신    │
   └─────────────────┼─────────────────┘
                     │
                     ▼
        CodeEntity 리스트 (호출 해석 완료)
```

---

## 1단계: JavaParser — 파일을 AST로 변환

```python
# java_parser.py
parser = JavaParser()
tree, source = parser.parse_file(Path("OrderService.java"))
```

### 내부에서 일어나는 일

```
OrderService.java
       │
       ▼  file_path.read_bytes()
바이트 데이터 (source)
  b'package com.example.order;\n\n/** ...'
       │
       ▼  self.parser.parse(source)
AST Tree 객체
  └── tree.root_node  ← 여기서부터 순회 시작
```

**핵심**: tree-sitter는 바이트 단위로 파싱한다. 모든 Node는 텍스트를 갖고 있지 않고,
원본 바이트에서의 **위치**(start_byte, end_byte)만 갖고 있다.

```python
# Node에서 텍스트를 꺼내는 유일한 방법:
text = source[node.start_byte:node.end_byte].decode("utf-8")
```

---

## 1단계 결과: AST 트리 전체 구조

tree-sitter가 위의 Java 파일을 파싱하면 이 트리가 만들어진다:

```
program ─────────────────────────────────────────── root_node
│
├── package_declaration
│   ├── "package"
│   ├── scoped_identifier ─────────── "com.example.order"
│   └── ";"
│
├── block_comment ─────────────────── "/** 주문 처리 서비스 */"
│
└── class_declaration
    ├── modifiers
    │   ├── marker_annotation ─────── @Service
    │   │   └── name: "Service"
    │   └── "public"
    │
    ├── "class"
    ├── name: "OrderService" ──────── identifier
    │
    └── body: class_body
        │
        ├── field_declaration
        │   ├── modifiers: "private", "final"
        │   ├── type: "OrderRepository" ──── type_identifier
        │   └── variable_declarator
        │       └── name: "orderRepo" ────── identifier
        │
        ├── block_comment ─────────────────── (Javadoc 없음)
        │
        ├── constructor_declaration
        │   ├── modifiers
        │   │   └── annotation ────────────── @Autowired
        │   ├── name: "OrderService"
        │   ├── parameters
        │   │   └── formal_parameter
        │   │       ├── type: "OrderRepository"
        │   │       └── name: "orderRepo"
        │   └── body (block)
        │       └── expression_statement
        │           └── assignment: this.orderRepo = orderRepo
        │
        ├── block_comment ─────────────────── "/** 주문을 생성한다. ... */"
        │
        ├── method_declaration ─────────────── create 메서드
        │   ├── modifiers
        │   │   ├── annotation ────────────── @Transactional
        │   │   └── "public"
        │   ├── type: "OrderDto" ──────────── 반환 타입
        │   ├── name: "create"
        │   ├── parameters
        │   │   └── formal_parameter
        │   │       ├── type: "OrderRequest"
        │   │       └── name: "req"
        │   └── body (block)
        │       ├── expression_statement
        │       │   └── method_invocation ─── validate(req)
        │       │       ├── name: "validate"
        │       │       └── arguments: (req)
        │       │
        │       ├── local_variable_declaration
        │       │   └── ... orderRepo.save(req.toEntity())
        │       │       └── method_invocation
        │       │           ├── object: "orderRepo"
        │       │           ├── name: "save"
        │       │           └── arguments
        │       │               └── method_invocation
        │       │                   ├── object: "req"
        │       │                   ├── name: "toEntity"
        │       │                   └── arguments: ()
        │       │
        │       └── return_statement
        │           └── method_invocation ─── OrderDto.from(order)
        │               ├── object: "OrderDto"
        │               ├── name: "from"
        │               └── arguments: (order)
        │
        └── method_declaration ─────────────── validate 메서드
            ├── modifiers: "private"
            ├── type: "void"
            ├── name: "validate"
            ├── parameters
            │   └── formal_parameter
            │       ├── type: "OrderRequest"
            │       └── name: "req"
            └── body (block)
                └── if_statement
                    └── ...
                        └── method_invocation
                            ├── object: "req"
                            ├── name: "getAmount"
                            └── arguments: ()
```

이 트리의 각 노드를 코드가 어떻게 읽어가는지 아래에서 추적한다.

---

## 2단계: EntityExtractor — AST를 순회하며 엔티티 추출

```python
# extractors.py
extractor = EntityExtractor()
entities = extractor.extract(tree, source, file_path)
```

### extract() 진입

```python
def extract(self, tree, source, file_path):
    entities = []
    # ① 패키지명 추출
    package_name = self._extract_package(tree.root_node, source)
    # ② 선언문 순회 시작
    self._walk_declarations(tree.root_node, source, file_path, package_name, None, entities)
    return entities
```

---

### ① _extract_package() — 패키지명 추출

root_node의 자식을 순회하다가 `package_declaration`을 찾는다:

```
program (root_node)
├── package_declaration    ◄── 이것을 찾음
│   ├── "package"
│   ├── scoped_identifier  ◄── 여기서 텍스트 추출
│   └── ";"
├── block_comment
└── class_declaration
```

```python
def _extract_package(self, root, source):
    for child in root.children:          # program의 자식 3개를 순회
        if child.type == "package_declaration":   # ✓ 첫 번째에서 발견
            for sub in child.children:
                if sub.type == "scoped_identifier":   # ✓ 발견
                    return source[sub.start_byte:sub.end_byte].decode("utf-8")
                    #      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                    #      → "com.example.order"
```

**결과**: `package_name = "com.example.order"`

---

### ② _walk_declarations() — 선언문 탐색

root_node의 자식을 순회하며 **선언문 타입**을 찾는다:

```
program (root_node)의 자식 3개:

  [0] package_declaration    → 타입이 class/interface/enum이 아님 → 건너뜀
  [1] block_comment          → 건너뜀
  [2] class_declaration      → ✓ 발견! _extract_class_like() 호출
```

```python
def _walk_declarations(self, node, source, file_path, package_name, enclosing_class, entities):
    for child in node.children:
        if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            self._extract_class_like(child, ...)   # ◄── class_declaration 발견 시
```

---

### ③ _extract_class_like() — 클래스 엔티티 생성

`class_declaration` 노드를 받아서 처리한다.

**A. 기본 정보 추출**

```
class_declaration
├── modifiers
│   ├── marker_annotation → @Service      ◄── extract_annotations()이 찾음
│   └── "public"                          ◄── extract_modifiers()가 찾음
├── name: "OrderService"                  ◄── _get_name()이 찾음
└── body: class_body                      ◄── 나중에 멤버 순회에 사용
```

각 헬퍼 함수가 하는 일:

```
┌─ _get_name(node, source) ─────────────────────────────────┐
│                                                            │
│  node.child_by_field_name("name")                         │
│  → identifier 노드를 직접 가져옴                           │
│  → source[start_byte:end_byte] → "OrderService"           │
└────────────────────────────────────────────────────────────┘

┌─ extract_annotations(node, source) ── comment_extractor.py ─┐
│                                                              │
│  node.children에서 modifiers를 찾고                          │
│  modifiers.children에서 marker_annotation/annotation을 찾아  │
│  name 필드에서 텍스트 추출 후 "@" 붙임                        │
│                                                              │
│  modifiers                                                   │
│  ├── marker_annotation                                       │
│  │   └── name: "Service"  → "@Service"                      │
│  └── "public" (어노테이션 아님 → 무시)                       │
│                                                              │
│  결과: ["@Service"]                                          │
└──────────────────────────────────────────────────────────────┘

┌─ extract_modifiers(node, source) ── comment_extractor.py ──┐
│                                                             │
│  modifiers.children에서 어노테이션이 아닌 것만 수집          │
│                                                             │
│  modifiers                                                  │
│  ├── marker_annotation → 어노테이션이므로 건너뜀            │
│  └── "public"          → ✓ 수집                             │
│                                                             │
│  결과: ["public"]                                           │
└─────────────────────────────────────────────────────────────┘

┌─ extract_javadoc(node, source) ── comment_extractor.py ────┐
│                                                             │
│  node.prev_named_sibling을 확인한다.                        │
│  class_declaration의 바로 이전 형제 노드는?                  │
│                                                             │
│  program                                                    │
│  ├── package_declaration                                    │
│  ├── block_comment  ◄── 이것이 prev_named_sibling          │
│  └── class_declaration (현재 node)                          │
│                                                             │
│  block_comment의 텍스트가 "/**"로 시작하는가?               │
│  → "/** 주문 처리 서비스 */" → ✓ "/**"로 시작               │
│                                                             │
│  결과: "/** 주문 처리 서비스 */"                             │
└─────────────────────────────────────────────────────────────┘

┌─ _qualify(package, class_name, name) ──────────────────────┐
│                                                             │
│  _qualify("com.example.order", None, "OrderService")       │
│  → None이 아닌 부분만 "."으로 조합                          │
│  → "com.example.order.OrderService"                         │
└─────────────────────────────────────────────────────────────┘
```

**CodeEntity #1 생성:**

```
CodeEntity(
    entity_type  = "class",
    name         = "OrderService",
    qualified_name = "com.example.order.OrderService",
    file_path    = "D:\\...\\OrderService.java",
    start_line   = 4,     ← node.start_point[0] + 1
    end_line     = 31,
    source_code  = "@Service\npublic class OrderService { ... }",
    class_name   = None,   ← 최상위 클래스이므로
    package_name = "com.example.order",
    modifiers    = ["public"],
    annotations  = ["@Service"],
    javadoc      = "/** 주문 처리 서비스 */",
)
```

**B. 클래스 본문 멤버 순회**

```python
body = node.child_by_field_name("body")    # → class_body 노드
for member in body.children:
    if member.type == "method_declaration":      # → _extract_method()
    elif member.type == "constructor_declaration": # → _extract_constructor()
    elif member.type == "field_declaration":       # → _extract_field()
    elif member.type in ("class_declaration", ...): # → 재귀 _extract_class_like()
```

class_body의 자식을 순회:

```
class_body
├── "{"                         → 타입 매칭 안 됨 → 건너뜀
├── field_declaration           → ✓ _extract_field() 호출
├── block_comment               → 건너뜀
├── constructor_declaration     → ✓ _extract_constructor() 호출
├── block_comment               → 건너뜀
├── method_declaration (create) → ✓ _extract_method() 호출
├── method_declaration (validate) → ✓ _extract_method() 호출
└── "}"                         → 건너뜀
```

---

### ④ _extract_field() — 필드 엔티티 생성

```
field_declaration
├── modifiers: "private", "final"
├── type: "OrderRepository"          ◄── child_by_field_name("type")
└── variable_declarator
    └── name: "orderRepo"            ◄── child_by_field_name("name")
```

일반 메서드/클래스와 다른 점: 필드는 `name`이 직접 child가 아니라
`variable_declarator` 안에 있다. 그래서 2단계로 접근한다:

```python
def _extract_field(self, node, source, ...):
    # 1단계: variable_declarator 찾기
    declarator = self._find_child(node, "variable_declarator")

    # 2단계: 그 안에서 name 가져오기
    name_node = declarator.child_by_field_name("name")
    name = source[name_node.start_byte:name_node.end_byte].decode("utf-8")
    # → "orderRepo"

    # 필드 타입 추출
    field_type = self._extract_field_type(node, source)
    # → node.child_by_field_name("type") → "OrderRepository"
```

**CodeEntity #2 생성:**

```
CodeEntity(
    entity_type  = "field",
    name         = "orderRepo",
    qualified_name = "com.example.order.OrderService.orderRepo",
    return_type  = "OrderRepository",    ← 필드 타입을 여기 저장!
    class_name   = "OrderService",
    modifiers    = ["private", "final"],
    ...
)
```

> **왜 필드 타입이 중요한가?**
> 나중에 call_graph.py에서 `orderRepo.save()` 를 `OrderRepository.save()`로 변환할 때
> 이 타입 정보를 사용한다. Spring DI로 주입된 의존성을 추적하는 핵심 메커니즘이다.

---

### ⑤ _extract_constructor() — 생성자 엔티티 생성

```
constructor_declaration
├── modifiers
│   └── annotation: @Autowired        ◄── 어노테이션 추출
├── name: "OrderService"
├── parameters
│   └── formal_parameter
│       ├── type: "OrderRepository"
│       └── name: "orderRepo"
└── body (block)
    └── ... this.orderRepo = orderRepo
```

메서드와 동일한 방식으로 추출하되, `return_type`이 없다.

**CodeEntity #3 생성:**

```
CodeEntity(
    entity_type  = "constructor",
    name         = "OrderService",
    qualified_name = "com.example.order.OrderService.OrderService",
    parameters   = ["OrderRepository orderRepo"],
    annotations  = ["@Autowired"],
    class_name   = "OrderService",
    ...
)
```

---

### ⑥ _extract_method() — create 메서드 엔티티 생성

```
method_declaration
├── modifiers
│   ├── annotation: @Transactional
│   └── "public"
├── type: "OrderDto"                  ◄── _extract_return_type()
├── name: "create"                    ◄── _get_name()
├── parameters                        ◄── _extract_parameters()
│   └── formal_parameter
│       ├── type: "OrderRequest"
│       └── name: "req"
└── body (block)                      ◄── _extract_method_invocations()가 여기를 탐색
    ├── method_invocation: validate(req)
    ├── method_invocation: orderRepo.save(...)
    │   └── arguments
    │       └── method_invocation: req.toEntity()
    └── method_invocation: OrderDto.from(order)
```

#### _extract_parameters() 상세

```python
params_node = node.child_by_field_name("parameters")
for child in params_node.children:
    if child.type == "formal_parameter":
        text = source[child.start_byte:child.end_byte].decode("utf-8")
        # → "OrderRequest req"
```

결과: `["OrderRequest req"]`

#### _extract_return_type() 상세

```python
type_node = node.child_by_field_name("type")
# → type_identifier 노드, 텍스트 = "OrderDto"
```

결과: `"OrderDto"`

#### _extract_method_invocations() 상세 — 호출 추출

메서드 본문(body)의 모든 자식을 **재귀적으로** 탐색하며
`method_invocation` 노드를 수집한다:

```python
def _collect_invocations(self, node, source, calls, seen):
    if node.type == "method_invocation":
        name_node = node.child_by_field_name("name")
        object_node = node.child_by_field_name("object")
        ...
    # 모든 자식도 재귀 탐색
    for child in node.children:
        self._collect_invocations(child, source, calls, seen)
```

재귀 탐색이 발견하는 4개의 method_invocation:

```
호출 1: validate(req)
┌──────────────────────────────────────────────────┐
│ method_invocation                                │
│ ├── object: (없음)   → 같은 클래스 내 호출       │
│ └── name: "validate"                             │
│                                                  │
│ object가 없으므로:                                │
│   call_str = "validate"                          │
└──────────────────────────────────────────────────┘

호출 2: orderRepo.save(req.toEntity())
┌──────────────────────────────────────────────────┐
│ method_invocation                                │
│ ├── object: "orderRepo"                          │
│ └── name: "save"                                 │
│                                                  │
│ object + "." + name:                             │
│   call_str = "orderRepo.save"                    │
└──────────────────────────────────────────────────┘

호출 3: req.toEntity()  ← 호출 2의 arguments 안에 중첩
┌──────────────────────────────────────────────────┐
│ method_invocation                                │
│ ├── object: "req"                                │
│ └── name: "toEntity"                             │
│                                                  │
│   call_str = "req.toEntity"                      │
└──────────────────────────────────────────────────┘

호출 4: OrderDto.from(order)
┌──────────────────────────────────────────────────┐
│ method_invocation                                │
│ ├── object: "OrderDto"                           │
│ └── name: "from"                                 │
│                                                  │
│   call_str = "OrderDto.from"                     │
└──────────────────────────────────────────────────┘
```

**중복 제거**: `seen` 집합으로 같은 call_str이 두 번 나오면 건너뜀.

#### Javadoc 추출

```
class_body의 자식 순서:
  ...
  block_comment  ← "/** 주문을 생성한다. ... */"
  method_declaration (create)  ← 현재 node
  ...

node.prev_named_sibling → block_comment
텍스트가 "/**"로 시작 → Javadoc!
```

**CodeEntity #4 생성:**

```
CodeEntity(
    entity_type  = "method",
    name         = "create",
    qualified_name = "com.example.order.OrderService.create",
    parameters   = ["OrderRequest req"],
    return_type  = "OrderDto",
    annotations  = ["@Transactional"],
    modifiers    = ["public"],
    javadoc      = "/**\n * 주문을 생성한다.\n * @param req 주문 요청\n */",
    class_name   = "OrderService",
    calls        = ["validate", "orderRepo.save", "req.toEntity", "OrderDto.from"],
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                    아직 미해석 상태! call_graph.py가 나중에 해석한다.
)
```

---

### ⑦ _extract_method() — validate 메서드 엔티티 생성

동일한 방식으로 추출.

**CodeEntity #5 생성:**

```
CodeEntity(
    entity_type  = "method",
    name         = "validate",
    qualified_name = "com.example.order.OrderService.validate",
    parameters   = ["OrderRequest req"],
    return_type  = "void",
    modifiers    = ["private"],
    class_name   = "OrderService",
    calls        = ["req.getAmount"],
)
```

---

## 2단계 결과: 총 5개의 CodeEntity

| # | type | name | calls (미해석) |
|---|------|------|----------------|
| 1 | class | OrderService | — |
| 2 | field | orderRepo | — |
| 3 | constructor | OrderService | — |
| 4 | method | create | validate, orderRepo.save, req.toEntity, OrderDto.from |
| 5 | method | validate | req.getAmount |

**이 시점에서 calls는 아직 미해석 상태다.** `"orderRepo.save"`에서 `orderRepo`가 어떤 타입인지 모른다.

---

## 3단계: CallGraph — 호출 관계 해석

```python
graph = CallGraph()
graph.resolve_invocations(all_entities)
```

### 해석 과정

`call_graph.py`는 `extract_field_types()`로 만든 필드 타입 맵을 사용한다:

```
필드 타입 맵:
{
    "OrderService": {
        "orderRepo": "OrderRepository"    ← field 엔티티의 return_type에서 가져옴
    }
}
```

create 메서드의 calls를 하나씩 해석한다:

```
미해석: "validate"
├── object 없음 → 같은 클래스 내 호출로 간주
├── 현재 클래스 = "OrderService"
├── "OrderService.validate" 검색 → ✓ 존재!
└── 해석 결과: "com.example.order.OrderService.validate"

미해석: "orderRepo.save"
├── object = "orderRepo"
├── 필드 타입 맵에서 OrderService의 "orderRepo" 찾기
├── → "OrderRepository"
├── "OrderRepository.save" 검색 → ✓ 존재! (다른 파일에 정의)
└── 해석 결과: "com.example.order.OrderRepository.save"

미해석: "req.toEntity"
├── object = "req"
├── "req"는 필드가 아님 (파라미터) → 필드 타입 맵에 없음
├── "?.toEntity"로 표시 (미해석)
└── 해석 결과: "?.toEntity"

미해석: "OrderDto.from"
├── object = "OrderDto" (대문자로 시작 → 클래스명으로 간주)
├── "OrderDto.from" 검색 → 존재 여부에 따라 해석
└── 해석 결과: "com.example.order.OrderDto.from" 또는 "?.from"
```

### 양방향 관계 갱신

해석된 호출로 **양방향 엣지**를 만든다:

```
create.calls = ["..OrderService.validate", "..OrderRepository.save", ...]
                        │                           │
                        ▼                           ▼
validate.called_by = ["..OrderService.create"]
                                        OrderRepository.save.called_by = ["..OrderService.create"]
```

---

## 최종 결과

```
CodeEntity #4 (해석 후):
  name: "create"
  calls: [
      "com.example.order.OrderService.validate",     ← "validate" → 같은 클래스 해석
      "com.example.order.OrderRepository.save",      ← "orderRepo.save" → 필드 타입 해석
      "?.toEntity",                                  ← 파라미터 호출 → 미해석
      "com.example.order.OrderDto.from",             ← 클래스 직접 호출 → 직접 매칭
  ]

CodeEntity #5 (해석 후):
  name: "validate"
  called_by: [
      "com.example.order.OrderService.create"        ← 역방향 관계 갱신
  ]
```

---

## 정리: 핵심 패턴

### Node 접근 패턴 2가지

```python
# 패턴 1: children 순회 — "어떤 타입이 있는지 모를 때"
for child in node.children:
    if child.type == "method_declaration":
        ...

# 패턴 2: field_name 접근 — "정확히 어떤 자식을 원하는지 알 때"
name_node = node.child_by_field_name("name")
type_node = node.child_by_field_name("type")
body_node = node.child_by_field_name("body")
```

### 텍스트 추출 패턴

```python
# Node는 위치만 갖고 있다. 텍스트는 항상 source에서 잘라낸다.
text = source[node.start_byte:node.end_byte].decode("utf-8")
```

### 재귀 순회 패턴

```python
# 깊이 우선 탐색으로 특정 타입의 노드를 모두 수집
def collect(node, source, results):
    if node.type == "찾는_타입":
        results.append(...)
    for child in node.children:
        collect(child, source, results)     # 자식도 전부 탐색
```

### 호출 해석 우선순위

```
1. 직접 매칭:   "OrderDto.from"    → 대문자로 시작하면 클래스명으로 검색
2. 필드 타입:   "orderRepo.save"   → 필드 타입 맵에서 타입 찾아서 변환
3. 같은 클래스: "validate"         → 현재 클래스에서 검색
4. 미해석:      "req.getAmount"    → "?.getAmount"로 표시
```
