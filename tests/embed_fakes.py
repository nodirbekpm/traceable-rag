"""Deterministic embeddings for tests: no model download, no ONNX runtime."""

import hashlib

from anchor.models import EMBEDDING_DIMENSIONS


class FakeEmbedder:
    """Deterministic vectors derived from the text; no model download."""

    model_name = "fake-embedder"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = dimensions
        self.calls = 0

    def _vector(self, value: str) -> list[float]:
        digest = hashlib.sha256(value.encode()).digest()
        return [digest[i % len(digest)] / 255 for i in range(self.dimensions)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
