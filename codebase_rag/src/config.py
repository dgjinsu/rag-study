"""
설정 관리 모듈.

pydantic-settings를 사용하여 .env 파일과 환경변수에서 설정을 로드한다.

사용 예:
    settings = Settings()
    print(settings.java_project_path)
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    애플리케이션 전역 설정.

    .env 파일 또는 환경변수에서 값을 읽어온다.
    필드명을 대문자로 변환한 환경변수와 매칭된다.
    예: java_project_path → JAVA_PROJECT_PATH
    """

    # 파싱 대상 Java 프로젝트의 루트 디렉토리
    java_project_path: Path = Path(r"D:\pwm\ui-backend\service\recipe")

    # 임베딩 설정 (Ollama 로컬)
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"          # ollama pull nomic-embed-text

    # ChromaDB 설정
    chroma_persist_dir: str = "data/chroma_db"
    chroma_collection_name: str = "codebase"

    # 청킹 설정
    max_chunk_lines: int = 60                          # 이 라인 수 초과 시 분할

    # pydantic-settings 설정: .env 파일 경로와 인코딩
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
