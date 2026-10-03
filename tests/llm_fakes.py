"""A scripted model for tests: returns canned JSON and records what it was asked."""

import json
from typing import Any

from anchor.llm import LLMResult


class FakeLLM:
    model_name = "fake-model"

    def __init__(self, facts: list[dict[str, Any]] | None = None, *, raw: str | None = None):
        self.raw = raw if raw is not None else json.dumps({"facts": facts or []})
        self.error: Exception | None = None
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        self.calls.append((system, user, schema))
        if self.error is not None:
            raise self.error
        return LLMResult(self.raw, input_tokens=1000, output_tokens=200, model_version="fake-001")


class FakeStreamingLLM:
    """Streams a canned answer in small pieces, like a real provider."""

    model_name = "fake-model"

    def __init__(self, answer: str, *, piece: int = 7) -> None:
        self.answer = answer
        self.piece = piece
        self.calls: list[tuple[str, str]] = []
        self._last_usage: LLMResult | None = None

    @property
    def last_usage(self) -> LLMResult | None:
        return self._last_usage

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        raise NotImplementedError

    def stream_text(self, system: str, user: str):
        self.calls.append((system, user))
        for start in range(0, len(self.answer), self.piece):
            yield self.answer[start : start + self.piece]
        self._last_usage = LLMResult(self.answer, 2000, 100, "fake-001")
