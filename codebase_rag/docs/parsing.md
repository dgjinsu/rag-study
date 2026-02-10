# Java 코드 파싱 — 어떻게 동작하는가

## 한 줄 요약

`.java` 파일을 tree-sitter로 AST(구문 트리)로 만들고, 그 트리를 순회하면서 클래스/메서드/필드 정보를 `CodeEntity` 객체로 뽑아낸다.

---

## 전체 흐름

```
OrderService.java (텍스트)
        │
        ▼  java_parser.py
AST (구문 트리)
        │
        ▼  extractors.py  +  comment_extractor.py
CodeEntity 리스트 (클래스, 메서드, 필드 각각 하나씩)
        │
        ▼  call_graph.py
CodeEntity 리스트 (calls/called_by가 해석된 상태)
```

---

## 1단계: Java 파일 → AST (`java_parser.py`)

### tree-sitter란?

- C로 작성된 범용 파서 프레임워크
- 언어별 문법 파일(grammar)을 플러그인으로 제공 → `tree-sitter-java`
- 정규식이나 문자열 검색과 달리, **문법을 이해하는 정확한 파싱**

### 동작

```python
parser = JavaParser()
tree, source = parser.parse_file(Path("OrderService.java"))
```

`parse_file()`이 하는 일:
1. 파일을 **바이트**로 읽는다 (`read_bytes()`)
2. tree-sitter `Parser.parse()`에 넘겨 AST를 생성한다
3. `(tree, source)` 튜플을 반환한다

바이트로 읽는 이유: tree-sitter는 바이트 레벨에서 동작한다. 노드에서 텍스트를 추출할 때 `source[node.start_byte:node.end_byte]`로 슬라이싱한다.

### AST가 뭔가?

이 Java 코드가:
```java
@Service
public class OrderService {
    public void process(OrderRequest req) {
        validate(req);
    }
}
```

이런 트리로 변환된다:
```
program
├── class_declaration
│   ├── modifiers
│   │   ├── marker_annotation  →  @Service
│   │   └── "public"
│   ├── name: "OrderService"
│   └── body (class_body)
│       └── method_declaration
│           ├── modifiers
│           │   └── "public"
│           ├── type: "void"
│           ├── name: "process"
│           ├── parameters
│           │   └── formal_parameter
│           │       ├── type: "OrderRequest"
│           │       └── name: "req"
│           └── body (block)
│               └── expression_statement
│                   └── method_invocation
│                       ├── name: "validate"
│                       └── arguments: (req)
```

모든 노드는 `type` (노드 종류), `children` (자식), `start_byte`/`end_byte` (원본 위치)를 가진다.

---

## 요약: 각 파일이 하는 일

| 파일 | 입력 | 출력 | 한 줄 설명 |
|------|------|------|-----------|
| `java_parser.py` | `.java` 파일 경로 | AST + 바이트 | tree-sitter로 Java를 구문 트리로 변환 |
| `comment_extractor.py` | AST 노드 | 문자열 리스트 | 노드에서 Javadoc, 어노테이션, 수정자 추출 |
| `extractors.py` | AST + 바이트 + 경로 | `CodeEntity` 리스트 | 트리를 순회하며 클래스/메서드/필드를 구조화된 객체로 변환 |
| `call_graph.py` | `CodeEntity` 리스트 | 해석된 `CodeEntity` 리스트 | 메서드 간 호출 관계를 해석하여 `calls`/`called_by` 갱신 |
