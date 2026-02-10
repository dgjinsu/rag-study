# 문서 기반 RAG 아키텍처

## 전체 플로우

```
┌─────────────────────────────────────────────────────────────────┐
│                      인덱싱 파이프라인 (run_index.py)              │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ 1. 로딩   │───→│ 2. 청킹   │───→│ 3. 임베딩 │───→│ 4. 저장   │  │
│  │ loader.py │    │chunker.py│    │          │    │          │  │
│  │          │    │          │    │  Ollama   │    │ ChromaDB │  │
│  │ .md 파일  │    │ Document  │    │  nomic-  │    │          │  │
│  │ → Document│    │ → Chunk   │    │  embed   │    │ 벡터 저장  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      질의 파이프라인 (run_query.py)               │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ 1. 질문   │───→│ 2. 검색   │───→│ 3. 프롬프트│───→│ 4. 답변   │  │
│  │          │    │          │    │   조합    │    │   생성    │  │
│  │ 사용자    │    │ ChromaDB │    │ 질문 +   │    │  Ollama  │  │
│  │ 한국어    │    │ 유사도    │    │ 검색결과  │    │  llama3  │  │
│  │ 질문 입력  │    │ top_k=5  │    │ → 프롬프트 │    │ → 한국어  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 파일별 역할

```
src/
├── config.py       ← 설정 (.env에서 로드)
├── loader.py       ← Step 1: .md 파일 → Document 객체
├── chunker.py      ← Step 2: Document → 작은 Chunk로 분할
├── indexer.py      ← Step 3~4: Chunk → 벡터 임베딩 → ChromaDB 저장
└── retriever.py    ← 질의: 질문 → 유사 문서 검색 → LLM 답변 생성
```

---

## 인덱싱 파이프라인 상세

### Step 1. 문서 로딩 (loader.py)

```
docs/k8s-ko/**/*.md  →  DirectoryLoader  →  list[Document]
```

- `DirectoryLoader`가 `docs/k8s-ko/` 하위 모든 `.md` 파일을 재귀 탐색
- 각 파일을 `TextLoader`로 읽어서 `Document` 객체로 변환
- YAML front matter (`--- ... ---`) 제거
- 첫 번째 `# 제목`을 추출하여 `metadata["title"]`에 저장

**Document 구조:**
```python
Document(
    page_content="# 파드\n파드는 쿠버네티스에서...",  # 마크다운 본문
    metadata={
        "source": "docs/k8s-ko/concepts/workloads/pods.md",
        "title": "파드"
    }
)
```

### Step 2. 문서 청킹 (chunker.py)

```
Document (긴 문서)  →  1차: 헤더 분할  →  2차: 크기 분할  →  list[Chunk]
```

**1차 분할 — MarkdownHeaderTextSplitter:**
- `#`, `##`, `###` 헤더를 기준으로 섹션 단위로 분리
- 각 청크에 `header_1`, `header_2`, `header_3` 메타데이터가 자동 추가됨

```
원본: "# 파드\n## 개요\n내용...\n## 생명주기\n내용..."
  ↓
chunk_1: "# 파드\n## 개요\n내용..."       metadata: {header_1: "파드", header_2: "개요"}
chunk_2: "# 파드\n## 생명주기\n내용..."   metadata: {header_1: "파드", header_2: "생명주기"}
```

**2차 분할 — RecursiveCharacterTextSplitter:**
- 1차에서 나온 섹션이 `chunk_size`(1000자)보다 크면 추가 분할
- `chunk_overlap`(200자)만큼 겹치게 잘라서 문맥 유실 방지
- 분할 우선순위: `\n\n` → `\n` → `. ` → ` ` → `""`

### Step 3~4. 임베딩 + 저장 (indexer.py)

```
list[Chunk]  →  OllamaEmbeddings  →  벡터(숫자 배열)  →  ChromaDB 저장
```

- 각 청크의 텍스트를 Ollama의 `nomic-embed-text` 모델로 벡터화
- 벡터 + 원문 + 메타데이터를 ChromaDB에 저장
- 저장 위치: `data/chroma_db/` (로컬 파일)

---

## 질의 파이프라인 상세 (retriever.py)

### LCEL 파이프라인

```python
chain = (
    {"context": retriever | _format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
```

이 한 줄이 아래 전체 흐름을 표현한다:

```
사용자 질문: "파드란 무엇인가요?"
         │
         ▼
┌─ retriever ─────────────────────────────┐
│ 1. 질문을 nomic-embed-text로 벡터화      │
│ 2. ChromaDB에서 코사인 유사도 검색       │
│ 3. 가장 유사한 문서 5개(top_k) 반환      │
└─────────────────────────────────────────┘
         │
         ▼
┌─ _format_docs ──────────────────────────┐
│ 검색된 5개 문서를 하나의 문자열로 결합     │
│                                         │
│ --- 문서 1 (출처: .../pods.md) ---       │
│ 파드는 쿠버네티스에서 생성하고...          │
│                                         │
│ --- 문서 2 (출처: .../overview.md) ---   │
│ ...                                     │
└─────────────────────────────────────────┘
         │
         ▼
┌─ prompt ────────────────────────────────┐
│ 다음 참고 문서를 바탕으로 질문에 답변하세요. │
│                                         │
│ [참고 문서]                              │
│ {위에서 조합된 context}                   │
│                                         │
│ [질문]                                   │
│ 파드란 무엇인가요?                        │
└─────────────────────────────────────────┘
         │
         ▼
┌─ llm (ChatOllama) ──────────────────────┐
│ Ollama llama3 모델이 프롬프트를 받아      │
│ 한국어로 답변 생성                        │
└─────────────────────────────────────────┘
         │
         ▼
┌─ StrOutputParser ───────────────────────┐
│ LLM 응답에서 텍스트만 추출               │
└─────────────────────────────────────────┘
         │
         ▼
  "파드는 쿠버네티스에서 배포할 수 있는
   가장 작은 컴퓨팅 단위입니다..."
```

---

## 사용하는 외부 서비스

```
┌─────────────┐         ┌─────────────┐
│   Ollama    │         │  ChromaDB   │
│ (localhost) │         │ (로컬 파일)  │
├─────────────┤         ├─────────────┤
│ 임베딩:      │         │ 벡터 저장소   │
│ nomic-embed │         │ 코사인 유사도  │
│ -text       │         │ 검색        │
│             │         │             │
│ LLM:        │         │ 위치:        │
│ llama3      │         │ data/       │
│             │         │ chroma_db/  │
└─────────────┘         └─────────────┘
  HTTP API                파일 기반
  :11434                  (서버 불필요)
```

---

## 실행 순서

```bash
# 0. 사전 준비
ollama pull nomic-embed-text
ollama pull llama3

# 1. 문서 다운로드 (최초 1회)
py scripts/download_docs.py

# 2. 인덱싱 (문서 변경 시 재실행)
py scripts/run_index.py

# 3. 질의
py scripts/run_query.py
```

## 설정 (.env)

| 변수 | 기본값 | 설명 |
|---|---|---|
| OLLAMA_BASE_URL | http://localhost:11434 | Ollama 서버 주소 |
| EMBEDDING_MODEL | nomic-embed-text | 임베딩 모델 |
| LLM_MODEL | llama3 | 답변 생성 LLM |
| CHROMA_PERSIST_DIR | data/chroma_db | 벡터 DB 저장 경로 |
| CHROMA_COLLECTION | k8s-docs-ko | 컬렉션 이름 |
| DOCS_DIR | docs/k8s-ko | 문서 디렉토리 |
| CHUNK_SIZE | 1000 | 청크 최대 글자 수 |
| CHUNK_OVERLAP | 200 | 청크 간 겹침 글자 수 |
| SEARCH_TOP_K | 5 | 검색 시 반환할 문서 수 |
