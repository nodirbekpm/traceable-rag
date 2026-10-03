"""Second-stage ordering of retrieved chunks. Two kinds are kept so they can be compared."""

import json
from dataclasses import replace
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from anchor.llm import LLMClient
from anchor.retrieval import Hit

DEFAULT_CROSS_ENCODER = "Xenova/ms-marco-MiniLM-L-6-v2"


class Reranker(Protocol):
    name: str

    def rerank(self, question: str, hits: list[Hit], k: int) -> list[Hit]: ...


def _ordered(hits: list[Hit], scores: list[float], k: int) -> list[Hit]:
    ranked = sorted(zip(hits, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [replace(hit, score=float(score)) for hit, score in ranked[:k]]


class NoReranker:
    name = "none"

    def rerank(self, question: str, hits: list[Hit], k: int) -> list[Hit]:
        return hits[:k]


class CrossEncoderReranker:
    """A small local cross-encoder: reads question and passage together, runs on CPU."""

    def __init__(self, model_name: str = DEFAULT_CROSS_ENCODER) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = f"cross-encoder:{model_name}"
        self._model = TextCrossEncoder(model_name)

    def rerank(self, question: str, hits: list[Hit], k: int) -> list[Hit]:
        if not hits:
            return []
        scores = list(self._model.rerank(question, [hit.text for hit in hits]))
        return _ordered(hits, scores, k)


class LLMReranker:
    """Asks the language model to grade each passage 0-10. Slower and costs tokens."""

    SCHEMA: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "score": {"type": "number", "minimum": 0, "maximum": 10},
                    },
                    "required": ["id", "score"],
                },
            }
        },
        "required": ["scores"],
    }
    SYSTEM = (
        "You grade how useful each passage is for answering the question. "
        'Return JSON {"scores": [{"id": <passage id>, "score": 0-10}]} with one entry '
        "per passage. 10 means the passage directly contains the answer."
    )

    def __init__(self, llm: LLMClient) -> None:
        self.name = f"llm:{llm.model_name}"
        self._llm = llm

    def rerank(self, question: str, hits: list[Hit], k: int) -> list[Hit]:
        if not hits:
            return []
        passages = "\n\n".join(f"[{i}] {hit.text}" for i, hit in enumerate(hits))
        result = self._llm.generate_json(
            self.SYSTEM, f"Question: {question}\n\nPassages:\n{passages}", self.SCHEMA
        )
        graded = {item["id"]: item["score"] for item in json.loads(result.text)["scores"]}
        # Ungraded passages sink but are not dropped.
        return _ordered(hits, [graded.get(i, -1.0) for i in range(len(hits))], k)


@lru_cache
def cross_encoder(model_name: str = DEFAULT_CROSS_ENCODER) -> CrossEncoderReranker:
    return CrossEncoderReranker(model_name)
