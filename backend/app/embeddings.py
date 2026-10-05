from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Local, open-source embeddings (ONNX) — no external API required."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]


def cosine_similarity(query: list[float], matrix: list[list[float]]) -> list[float]:
    if not matrix:
        return []
    q = np.asarray(query, dtype=np.float32)
    m = np.asarray(matrix, dtype=np.float32)
    denom = np.linalg.norm(m, axis=1) * (np.linalg.norm(q) or 1.0)
    denom[denom == 0] = 1.0
    return (m @ q / denom).tolist()
