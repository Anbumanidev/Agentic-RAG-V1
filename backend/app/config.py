from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (any open-source model served by Ollama or an OpenAI-compatible server such as
    # vLLM, llama.cpp server, LM Studio, LocalAI...)
    llm_provider: Literal["ollama", "openai_compatible"] = "ollama"
    llm_model: str = "qwen2.5:3b"
    llm_temperature: float = 0.2
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "http://localhost:8001/v1"
    openai_api_key: str = "not-needed"

    # Embeddings (local ONNX model via fastembed)
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Storage
    data_dir: Path = Path("./data")

    # Retrieval
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_k: int = 6
    # Chunks with cosine similarity below this value are ignored by the retriever.
    min_similarity: float = 0.3

    # Web research
    web_search_results: int = 10
    web_fetch_timeout: float = 12.0
    web_max_chars_per_page: int = 20000
    web_context_chunks: int = 8
    searxng_url: str | None = None

    # Memory
    memory_window: int = 10
    max_upload_mb: int = 25

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "agentic_rag.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()
