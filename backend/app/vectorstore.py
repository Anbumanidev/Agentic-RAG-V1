import uuid
from dataclasses import dataclass, field
from pathlib import Path

import chromadb

from app.embeddings import Embedder


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


class VectorStore:
    """Per-session knowledge base stored in a persistent ChromaDB collection."""

    def __init__(self, path: Path | None, embedder: Embedder):
        if path is None:
            self._client = chromadb.EphemeralClient()
        else:
            path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(path))
        self._embedder = embedder

    @staticmethod
    def _name(session_id: str) -> str:
        return f"session_{session_id.replace('-', '')}"

    def _collection(self, session_id: str):
        return self._client.get_or_create_collection(
            name=self._name(session_id), metadata={"hnsw:space": "cosine"}
        )

    def add(self, session_id: str, texts: list[str], metadatas: list[dict]) -> int:
        if not texts:
            return 0
        embeddings = self._embedder.embed(texts)
        self._collection(session_id).add(
            ids=[uuid.uuid4().hex for _ in texts],
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(texts)

    def search(self, session_id: str, query: str, k: int) -> list[Chunk]:
        collection = self._collection(session_id)
        count = collection.count()
        if count == 0:
            return []
        result = collection.query(
            query_embeddings=self._embedder.embed([query]),
            n_results=min(k, count),
        )
        chunks = []
        for text, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0], strict=False
        ):
            chunks.append(Chunk(text=text, metadata=dict(meta or {}), score=1.0 - float(dist)))
        return chunks

    def delete_document(self, session_id: str, document_id: str) -> None:
        self._collection(session_id).delete(where={"document_id": document_id})

    def delete_session(self, session_id: str) -> None:
        try:
            self._client.delete_collection(self._name(session_id))
        except Exception:  # noqa: BLE001 - collection may not exist
            pass
