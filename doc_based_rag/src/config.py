from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    llm_model: str = "llama3"

    # ChromaDB
    chroma_persist_dir: str = "data/chroma_db"
    chroma_collection: str = "k8s-docs-ko"

    # Documents
    docs_dir: str = "docs/k8s-ko"

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Search
    search_top_k: int = 5

    @property
    def docs_path(self) -> Path:
        return Path(self.docs_dir)

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)


settings = Settings()
