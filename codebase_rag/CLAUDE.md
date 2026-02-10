# Codebase RAG 프로젝트

## 목적

사내 코드베이스에 분산된 비즈니스 로직(검증 플로우, 알림 규칙 등)을 자연어로 질의응답할 수 있는 RAG 시스템 구축

## 대상

Java 코드베이스 (Git 저장소 기반)

## 구축 플로우

### 1. 코드 수집 및 전처리
- Python tree-sitter로 Java 코드를 AST 파싱
- 함수, 클래스, 모듈 등 의미 단위로 구조 추출
- 주석, docstring, 커밋 메시지, PR 설명 등 자연어 메타데이터도 함께 추출

### 2. Chunking
- 함수/메서드 단위 청킹 기본, 긴 함수는 논리 블록 단위 분할
- 메타데이터 부착: 파일 경로, 클래스명, 함수명, 호출 함수 목록, 모듈 설명
- call graph를 메타데이터로 저장 → 플로우 질문 대응

### 3. 임베딩 및 벡터 저장소
- 코드 특화 임베딩 모델 (OpenAI text-embedding-3-large, Voyage Code 2, CodeBERT 등 비교 예정)
- 벡터 DB: Chroma(프로토타입) → pgvector(운영) 고려
- 메타데이터 필터링 지원 필요

### 4. 검색 파이프라인
- 하이브리드 검색: 벡터 유사도 + BM25 키워드 검색
- Cross-Encoder 리랭킹
- call graph 기반 연쇄 검색 (플로우 추적)

### 5. LLM 통합
- Claude 또는 GPT-4o로 검색된 코드 청크 기반 답변 생성

### 6. 인터페이스
- Slack 봇 또는 웹 UI
