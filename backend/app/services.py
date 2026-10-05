from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from app.config import Settings
from app.embeddings import Embedder, FastEmbedder
from app.llm import build_llm
from app.memory import MemoryStore
from app.vectorstore import VectorStore
from app.web_search import WebSearcher


@dataclass
class Services:
    """Shared dependencies handed to every agent."""

    settings: Settings
    memory: MemoryStore
    store: VectorStore
    embedder: Embedder
    llm: BaseChatModel
    json_llm: BaseChatModel
    web: WebSearcher


def build_services(settings: Settings) -> Services:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    embedder = FastEmbedder(settings.embedding_model)
    return Services(
        settings=settings,
        memory=MemoryStore(settings.sqlite_path),
        store=VectorStore(settings.chroma_path, embedder),
        embedder=embedder,
        llm=build_llm(settings),
        json_llm=build_llm(settings, json_mode=True),
        web=WebSearcher(settings.searxng_url, settings.web_fetch_timeout),
    )
