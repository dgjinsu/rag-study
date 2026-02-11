"""검색 + LLM 답변 생성 모듈.

ChromaDB에서 유사 문서를 검색하고, Ollama LLM으로 답변을 생성한다.
LCEL(LangChain Expression Language) 파이프라인을 사용한다.
"""

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama

from src.config import settings
from src.indexer import get_vector_store

RAG_PROMPT_TEMPLATE = """\
다음 참고 문서를 바탕으로 질문에 답변하세요.

규칙:
- 답변은 한국어로 작성하세요.
- 참고 문서의 내용만을 기반으로 답변하세요.
- 문서에서 관련 내용을 찾을 수 없으면 "문서에서 관련 내용을 찾을 수 없습니다."라고 답하세요.
- 간결하고 명확하게 답변하세요.

[참고 문서]
{context}

[질문]
{question}
"""


def _format_docs(docs: list[Document]) -> str:
    """검색된 문서 리스트를 하나의 문자열로 포맷팅한다."""
    formatted = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "알 수 없음")
        formatted.append(f"--- 문서 {i} (출처: {source}) ---\n{doc.page_content}")
    return "\n\n".join(formatted)


def create_rag_chain():
    """RAG 체인을 생성한다.

    Returns:
        LCEL 파이프라인 (question → answer)
    """
    vector_store = get_vector_store()
    retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": settings.search_top_k},
    )

    prompt = ChatPromptTemplate.from_template(RAG_PROMPT_TEMPLATE)

    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
    )

    chain = (
        {"context": retriever | _format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain


def search_documents(
    query: str, top_k: int | None = None,
) -> list[tuple[Document, float]]:
    """벡터 스토어에서 유사 문서를 검색한다. (LLM 없이 검색만)

    Args:
        query: 검색 질의.
        top_k: 반환할 문서 수. None이면 설정값 사용.

    Returns:
        (Document, 유사도 점수) 튜플 리스트. 점수가 높을수록 유사.
    """
    vector_store = get_vector_store()
    k = top_k or settings.search_top_k
    return vector_store.similarity_search_with_relevance_scores(query, k=k)


def query(question: str) -> dict:
    """질문에 대한 RAG 답변을 생성한다.

    Args:
        question: 사용자 질문.

    Returns:
        {"answer": str, "sources": list[Document]}
    """
    # 검색 (유사도 점수 포함)
    search_results = search_documents(question)

    # 답변 생성
    chain = create_rag_chain()
    answer = chain.invoke(question)

    return {
        "answer": answer,
        "search_results": search_results,
    }
