import hashlib
import json
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from app.config import Settings
from app.main import create_app
from app.memory import MemoryStore
from app.services import Services
from app.vectorstore import VectorStore
from app.web_search import SearchResult, WebPage


class FakeChatModel(BaseChatModel):
    """Deterministic chat model: `responder` maps the message list to a reply."""

    responder: Callable[[list[BaseMessage]], str]

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = self.responder(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(text))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        for word in self.responder(messages).split(" "):
            yield ChatGenerationChunk(message=AIMessageChunk(content=word + " "))


class HashEmbedder:
    """Bag-of-words hashing embedder so semantic search works without a model download."""

    dims = 256

    def embed(self, texts):
        out = []
        for text in texts:
            vec = [0.0] * self.dims
            for token in text.lower().split():
                token = "".join(ch for ch in token if ch.isalnum())
                if token:
                    vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0
            out.append(vec)
        return out


class FakeWeb:
    def __init__(self):
        self.queries = []

    async def search(self, query, max_results=10):
        self.queries.append(query)
        return [
            SearchResult(f"Result {i}", f"https://example.com/{i}", f"snippet {i}")
            for i in range(1, max_results + 1)
        ]

    async def fetch_pages(self, results, max_chars=20000):
        return [
            WebPage(
                r.title, r.url, r.snippet, f"{r.title} says the capital of Mars is Olympus.", True
            )
            for r in results
        ]


def planner_json(messages) -> str:
    last = messages[-1].content
    question = last.split("Latest user message:")[-1].strip()
    route = "conversation" if "my name" in question.lower() else "research"
    return json.dumps({"standalone_question": question, "route": route})


def default_json_responder(messages) -> str:
    system = messages[0].content
    if "Planner" in system:
        return planner_json(messages)
    if "Grader" in system:
        relevant = "bananas" not in messages[-1].content.lower()
        return json.dumps({"relevant": relevant, "reason": "test"})
    return "{}"


def default_responder(messages) -> str:
    system = messages[0].content
    if "web search results" in system:
        return "From the web: Olympus [1]."
    if "summary/overview of their loaded documents" in system:
        return "Summary of your documents [1]."
    if "loaded URLs and files" in system:
        return "From your documents: the secret code is 42 [1]."
    if "just loaded new content" in system:
        return "Loaded the page. Ask me anything."
    history = " ".join(m.content for m in messages[1:])
    if "Anbu" in history:
        return "Your name is Anbu."
    return "Hello!"


@pytest.fixture
def services(tmp_path):
    settings = Settings(data_dir=tmp_path, min_similarity=0.05)
    embedder = HashEmbedder()
    return Services(
        settings=settings,
        memory=MemoryStore(tmp_path / "test.db"),
        store=VectorStore(tmp_path / "chroma", embedder),
        embedder=embedder,
        llm=FakeChatModel(responder=default_responder),
        json_llm=FakeChatModel(responder=default_json_responder),
        web=FakeWeb(),
    )


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as c:
        yield c


def read_events(response) -> list[dict]:
    return [
        json.loads(line[len("data: ") :])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
