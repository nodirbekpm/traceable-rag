"""Text embeddings behind one interface. The default runs locally on CPU, free of charge."""

from functools import lru_cache
from typing import Protocol

from anchor.config import Settings


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """ONNX model run through fastembed: no GPU, no PyTorch, no API key."""

    def __init__(self, model_name: str, *, batch_size: int = 64) -> None:
        # Imported lazily: loading onnxruntime is slow and tests never need it.
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name)
        self._batch_size = batch_size
        self.dimensions = len(self.embed_query("dimension probe"))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts, batch_size=self._batch_size)]

    def embed_query(self, text: str) -> list[float]:
        # Retrieval models are trained with a distinct query prefix; fastembed applies it.
        return next(iter(self._model.query_embed(text))).tolist()


@lru_cache
def _cached(model_name: str) -> Embedder:
    return FastEmbedEmbedder(model_name)


def build_embedder(settings: Settings) -> Embedder:
    return _cached(settings.embedding_model)
