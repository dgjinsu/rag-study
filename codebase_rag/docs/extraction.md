# 엔티티 추출 프로세스 — extractors.py 상세

## 한 줄 요약

AST 트리를 위에서 아래로 순회하면서, 선언문(클래스/메서드/필드)을 만날 때마다 `CodeEntity` 객체를 하나씩 만든다.

---

## 사전 지식: tree-sitter Node란?

tree-sitter가 Java 소스를 파싱하면 **트리(나무 구조)**를 만든다. 이 트리의 각 칸 하나가 `Node`다.

### Node가 가진 데이터

```
Node 하나
├── type              어떤 종류인지 (문자열)
│                     "class_declaration", "method_declaration", "identifier" 등
│
├── start_byte        원본 소스에서 이 노드가 시작하는 바이트 위치
├── end_byte          원본 소스에서 이 노드가 끝나는 바이트 위치
│                     → 텍스트 추출: source[start_byte:end_byte]
│
├── start_point       (행, 열) 튜플  예: (2, 0)은 3번째 줄 첫 칸 (0-based)
├── end_point         (행, 열) 튜플
│
├── children          자식 Node 리스트
├── parent            부모 Node
├── prev_named_sibling  이전 형제 Node (Javadoc 찾기에 사용)
├── next_named_sibling  다음 형제 Node
│
└── child_by_field_name("name")   이름으로 특정 자식에 바로 접근
```

### 핵심: Node에는 텍스트가 없다

Node는 **"원본 소스에서 몇 번째 바이트부터 몇 번째까지"**라는 위치 정보만 갖고 있다.
실제 텍스트를 얻으려면 원본 소스(`source`)에서 잘라내야 한다:

```python
# Node에서 텍스트 꺼내는 유일한 방법
text = source[node.start_byte:node.end_byte].decode("utf-8")
```

그래서 extractors.py의 모든 함수에 `node`와 `source`가 항상 짝으로 전달된다.

### 실제 예시

이 Java 코드를 파싱하면:
```java
@Service
public class OrderService {
    private final OrderRepository orderRepo;

    public OrderDto create(OrderRequest req) {
        orderRepo.save(req);
    }
}
```

이런 Node 트리가 생긴다:
```
program                              ← root_node (type="program")
└── class_declaration                ← type="class_declaration"
    ├── modifiers                    ← children[0]
    │   ├── marker_annotation        ← @Service
    │   └── "public"
    ├── "class"                      ← class 키워드
    ├── identifier "OrderService"    ← child_by_field_name("name")으로 접근 가능
    └── class_body                   ← child_by_field_name("body")로 접근 가능
        ├── "{"
        ├── field_declaration
        │   ├── modifiers: "private", "final"
        │   ├── type_identifier: "OrderRepository"     ← child_by_field_name("type")
        │   └── variable_declarator
        │       └── identifier: "orderRepo"            ← child_by_field_name("name")
        ├── method_declaration
        │   ├── modifiers: "public"
        │   ├── type_identifier: "OrderDto"            ← child_by_field_name("type")
        │   ├── identifier: "create"                   ← child_by_field_name("name")
        │   ├── formal_parameters                      ← child_by_field_name("parameters")
        │   │   └── formal_parameter
        │   │       ├── type: "OrderRequest"
        │   │       └── name: "req"
        │   └── block (메서드 본문)
        │       └── expression_statement
        │           └── method_invocation
        │               ├── object: "orderRepo"        ← child_by_field_name("object")
        │               ├── name: "save"               ← child_by_field_name("name")
        │               └── arguments: (req)
        └── "}"
```

### Node 접근 방법 2가지

**1. children으로 순회** — 자식 노드를 하나씩 돌면서 type을 확인:
```python
for child in node.children:
    if child.type == "method_declaration":
        # 메서드 발견!
```

**2. child_by_field_name()으로 직접 접근** — 이름으로 특정 자식을 바로 가져옴:
```python
name_node = node.child_by_field_name("name")    # → identifier "create"
type_node = node.child_by_field_name("type")    # → type_identifier "OrderDto"
body_node = node.child_by_field_name("body")    # → block { ... }
```

extractors.py는 이 두 가지를 상황에 따라 섞어 쓴다:
- `_walk_declarations()` — children 순회로 선언문 탐색
- `_get_name()` — `child_by_field_name("name")`으로 이름 바로 접근
- `_extract_return_type()` — `child_by_field_name("type")`으로 타입 바로 접근

---

## 입력과 출력

```
입력: tree (AST), source (바이트), file_path (경로)
출력: CodeEntity 리스트
```

예시:
```python
extractor = EntityExtractor()
entities = extractor.extract(tree, source, file_path)
# → [CodeEntity(class), CodeEntity(field), CodeEntity(method), ...]
```

---

## 전체 프로세스 흐름

```
extract()
  │
  │  ① 패키지명 추출
  ├── _extract_package(root_node, source)
  │     → "com.mirero.pwm.recipe.domain.thk.memory.rvs.aleris.validator"
  │
  │  ② 루트 노드의 자식을 순회
  └── _walk_declarations(root_node, ...)
        │
        │  class_declaration 발견!
        └── _extract_class_like(node, ...)
              │
              │  ③ 클래스 자체를 CodeEntity로 생성
              ├── name         ← _get_name(node, source)
              ├── qualified    ← _qualify(package, None, name)
              ├── annotations  ← extract_annotations(node, source)  ← comment_extractor.py
              ├── modifiers    ← extract_modifiers(node, source)    ← comment_extractor.py
              ├── javadoc      ← extract_javadoc(node, source)      ← comment_extractor.py
              ├── source_code  ← source[start_byte:end_byte]
              ├── start_line   ← node.start_point[0] + 1
              └── entities.append(CodeEntity(...))
              │
              │  ④ class_body 안의 멤버를 하나씩 순회
              └── for member in body.children:
                    │
                    ├── method_declaration  → _extract_method()
                    ├── constructor_declaration → _extract_constructor()
                    ├── field_declaration → _extract_field()
                    └── class_declaration (중첩) → _extract_class_like() (재귀)
```

---

## 단계별 상세

### ① 패키지명 추출 — `_extract_package()`

```java
package com.mirero.pwm.recipe.domain;  // ← 이 줄에서 추출
```

AST에서의 구조:
```
program
└── package_declaration
    └── scoped_identifier  →  "com.mirero.pwm.recipe.domain"
```

`root.children`을 순회하다가 `package_declaration`을 발견하면, 그 안의 `scoped_identifier` 노드에서 텍스트를 꺼낸다.

**왜 필요한가**: `qualified_name`을 만들 때 패키지명이 앞에 붙는다.
- 패키지 없으면: `MemoryDieSizeValidator.validate`
- 패키지 있으면: `com.mirero.pwm.recipe.domain.MemoryDieSizeValidator.validate`

---

### ② 선언문 탐색 — `_walk_declarations()`

루트 노드의 자식들을 순회하며 **선언문 타입**을 찾는다:

| 찾는 노드 타입 | 의미 | 처리 |
|----------------|------|------|
| `class_declaration` | 클래스 선언 | → `_extract_class_like()` |
| `interface_declaration` | 인터페이스 선언 | → `_extract_class_like()` |
| `enum_declaration` | enum 선언 | → `_extract_class_like()` |
| `class_body` | 클래스 본문 | → 재귀로 내부 탐색 |

나머지 노드 타입(`import_declaration`, `line_comment` 등)은 무시한다.

---

### ③ 클래스 추출 — `_extract_class_like()`

```java
@Component
public class MemoryDieSizeValidator {
    ...
}
```

이 선언문에서 추출하는 항목:

```
name           = "MemoryDieSizeValidator"
                 └── _get_name(): node의 name 필드에서 추출

qualified_name = "com.mirero...validator.MemoryDieSizeValidator"
                 └── _qualify(): 패키지 + 클래스명 조합

annotations    = ["@Component"]
                 └── comment_extractor.extract_annotations()
                     modifiers 노드 안의 marker_annotation/annotation에서 추출

modifiers      = ["public"]
                 └── comment_extractor.extract_modifiers()
                     modifiers 노드 안에서 어노테이션이 아닌 것만 수집

javadoc        = "/** 메모리 다이 사이즈 검증기 */"  (있으면)
                 └── comment_extractor.extract_javadoc()
                     node의 바로 이전 형제(prev_named_sibling)가 /** 블록 주석인지 확인

source_code    = 클래스 전체 소스 텍스트
                 └── source[node.start_byte:node.end_byte].decode("utf-8")

start_line     = 1-based 시작 라인
                 └── node.start_point[0] + 1  (tree-sitter는 0-based)

end_line       = 1-based 종료 라인
                 └── node.end_point[0] + 1
```

추출 후 `entities.append(CodeEntity(...))`로 리스트에 추가한다.

그 다음, **클래스 본문(class_body)** 안의 멤버를 순회하며 ④로 넘어간다.

---

### ④-A 메서드 추출 — `_extract_method()`

```java
@Override
public FieldValidationResult validate(AlerisRecipe recipe, ReferenceData refData) {
    DieSizeInfo dieSize = recipe.getDieSize();
    refData.checkRange(dieSize);
    return FieldValidationResult.success();
}
```

클래스와 동일한 항목에 **추가로** 추출하는 것:

```
parameters  = ["AlerisRecipe recipe", "ReferenceData refData"]
              └── _extract_parameters()
                  parameters 노드의 formal_parameter 자식들에서 텍스트 추출

return_type = "FieldValidationResult"
              └── _extract_return_type()
                  method_declaration의 type 필드에서 추출

calls       = ["recipe.getDieSize", "refData.checkRange", "FieldValidationResult.success"]
              └── _extract_method_invocations()
                  메서드 본문의 method_invocation 노드를 재귀 수집
```

**calls 추출 과정** (`_collect_invocations`):

```
method_invocation 노드 구조:
    ├── object: "recipe"           (호출 대상)
    ├── name: "getDieSize"         (메서드명)
    └── arguments: ()

→ call_str = "recipe.getDieSize"
```

object가 없으면 같은 클래스 내 호출:
```java
validate(req);  // object 없음 → call_str = "validate"
```

object에 `.`이 포함된 체이닝:
```java
a.b().c().d();  // object = "a.b().c()" → "." 기준 마지막 = "c()" → 단순화
```

---

### ④-B 생성자 추출 — `_extract_constructor()`

메서드와 동일하지만:
- `entity_type = "constructor"`
- `return_type`은 없음

---

### ④-C 필드 추출 — `_extract_field()`

```java
private final OrderRepository orderRepo;
```

AST 구조:
```
field_declaration
├── modifiers: "private", "final"
├── type: "OrderRepository"          ← 필드 타입
└── variable_declarator
    └── name: "orderRepo"            ← 필드명
```

추출 항목:
```
name        = "orderRepo"
              └── variable_declarator → name 필드

return_type = "OrderRepository"       ← 필드 타입을 return_type에 저장
              └── _extract_field_type()
                  field_declaration의 type 필드
```

**필드 타입이 중요한 이유**: 나중에 `call_graph.py`에서 `orderRepo.save()` 호출을 `OrderRepository.save()`로 해석할 때 사용한다.

---

### ④-D 중첩 클래스 — 재귀

```java
public class Outer {
    static class Inner {        // ← 중첩 클래스
        void doSomething() {}
    }
}
```

`class_body` 안에서 또 `class_declaration`을 발견하면, `_extract_class_like()`를 재귀 호출한다.
이때 `enclosing_class = "Outer"`가 전달되어, Inner의 qualified_name은 `패키지.Outer.Inner`가 된다.

---

## 헬퍼 함수들

### `_get_name(node, source)` → `str | None`

노드의 `name` 필드에서 식별자 텍스트를 추출한다.
```python
name_node = node.child_by_field_name("name")
# → source[name_node.start_byte:name_node.end_byte].decode("utf-8")
```

### `_qualify(package, class_name, name)` → `str`

패키지, 클래스명, 이름을 `.`으로 조합한다.
```python
_qualify("com.example", "OrderService", "create")
# → "com.example.OrderService.create"

_qualify("com.example", None, "OrderService")
# → "com.example.OrderService"
```

### `_find_child(node, child_type)` → `Node | None`

특정 타입의 자식 노드를 찾는다. `_extract_field()`에서 `variable_declarator`를 찾을 때 사용.

---

## 모듈 레벨 함수: `extract_field_types()`

이 함수는 `EntityExtractor` 클래스 바깥에 정의된 독립 함수다.
`call_graph.py`에서 호출한다.

```python
field_types = extract_field_types(all_entities)
# → {"OrderService": {"orderRepo": "OrderRepository", "validator": "Validator"}}
```

모든 field 엔티티를 순회하면서 `{클래스명: {필드명: 필드타입}}` 맵을 만든다.

제네릭 타입은 `<` 이전만 사용:
```
List<OrderDto> → "List"
Map<String, Object> → "Map"
OrderRepository → "OrderRepository" (그대로)
```

---

## 하나의 Java 파일이 처리되는 예시

```java
package com.example;

/** 주문 서비스 */
@Service
public class OrderService {
    private final OrderRepository orderRepo;

    public OrderDto create(OrderRequest req) {
        validate(req);
        return orderRepo.save(req);
    }

    private void validate(OrderRequest req) { ... }
}
```

추출 결과:

| # | entity_type | name | qualified_name | 비고 |
|---|-------------|------|----------------|------|
| 1 | class | OrderService | com.example.OrderService | annotations=["@Service"], javadoc="/** 주문 서비스 */" |
| 2 | field | orderRepo | com.example.OrderService.orderRepo | return_type="OrderRepository" |
| 3 | method | create | com.example.OrderService.create | parameters=["OrderRequest req"], return_type="OrderDto", calls=["validate", "orderRepo.save"] |
| 4 | method | validate | com.example.OrderService.validate | parameters=["OrderRequest req"], modifiers=["private"] |

총 4개의 `CodeEntity`가 생성된다.
