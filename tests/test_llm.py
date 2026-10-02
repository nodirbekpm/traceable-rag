import json
from decimal import Decimal

import httpx
import pytest

from anchor.config import Settings
from anchor.llm import GeminiClient, LLMError, LLMResult, build_llm, cost_usd

REPLY = {
    "candidates": [{"content": {"parts": [{"text": '{"facts": '}, {"text": "[]}"}]}}],
    "usageMetadata": {
        "promptTokenCount": 1200,
        "candidatesTokenCount": 30,
        "thoughtsTokenCount": 70,
    },
    "modelVersion": "gemini-test-001",
}


def client(handler) -> GeminiClient:
    return GeminiClient("secret-key", "gemini-test", transport=httpx.MockTransport(handler))


def test_request_carries_key_schema_and_prompts() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=REPLY)

    result = client(handler).generate_json("system text", "user text", {"type": "object"})

    request = seen[0]
    body = json.loads(request.content)
    assert request.url.path == "/v1beta/models/gemini-test:generateContent"
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in str(request.url)
    assert body["systemInstruction"]["parts"][0]["text"] == "system text"
    assert body["contents"][0]["parts"][0]["text"] == "user text"
    assert body["generationConfig"]["responseJsonSchema"] == {"type": "object"}
    assert body["generationConfig"]["temperature"] == 0
    assert result == LLMResult('{"facts": []}', 1200, 100, "gemini-test-001")


def test_http_error_is_reported_with_status() -> None:
    with pytest.raises(LLMError, match="HTTP 429"):
        client(lambda request: httpx.Response(429, text="quota")).generate_json("s", "u", {})


def test_blocked_or_empty_reply_is_an_error() -> None:
    blocked = {"promptFeedback": {"blockReason": "SAFETY"}}

    with pytest.raises(LLMError, match="no content"):
        client(lambda request: httpx.Response(200, json=blocked)).generate_json("s", "u", {})


def test_missing_key_is_rejected_before_any_request() -> None:
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiClient("", "gemini-test")


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(LLMError, match="Unknown LLM_PROVIDER"):
        build_llm(Settings(llm_provider="nope"))


def test_cost_uses_list_prices_per_million_tokens() -> None:
    settings = Settings(llm_price_input_per_mtok="0.30", llm_price_output_per_mtok="2.50")

    assert cost_usd(LLMResult("", 1_000_000, 100_000, "m"), settings) == Decimal("0.55")
