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


SLEEPS: list[float] = []


def client(handler, max_retries: int = 0) -> GeminiClient:
    """Retries are off unless a test is about retries; sleeping is recorded, never real."""
    SLEEPS.clear()
    return GeminiClient(
        "secret-key",
        "gemini-test",
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        sleep=SLEEPS.append,
    )


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


def test_streaming_yields_text_pieces_and_records_usage() -> None:
    events = [
        {"candidates": [{"content": {"parts": [{"text": '{"claim": '}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "x", "thought": True}]}}]},
        {
            "candidates": [{"content": {"parts": [{"text": '"ok"}\n'}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 12},
            "modelVersion": "gemini-test-002",
        },
    ]
    body = "".join(f"data: {json.dumps(event)}\r\n\r\n" for event in events)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    gemini = client(handler)
    pieces = list(gemini.stream_text("system", "user"))

    assert pieces == ['{"claim": ', '"ok"}\n']
    assert seen[0].url.params["alt"] == "sse"
    assert seen[0].url.path.endswith(":streamGenerateContent")
    assert gemini.last_usage == LLMResult('{"claim": "ok"}\n', 900, 12, "gemini-test-002")


def test_streaming_http_error_is_reported() -> None:
    gemini = client(lambda request: httpx.Response(429, text="quota exceeded"))

    with pytest.raises(LLMError, match="HTTP 429: quota exceeded"):
        list(gemini.stream_text("s", "u"))


QUOTA = {
    "error": {
        "code": 429,
        "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "37s"}],
    }
}


def test_rate_limit_waits_the_advertised_delay_and_retries() -> None:
    replies = iter([httpx.Response(429, json=QUOTA), httpx.Response(200, json=REPLY)])

    result = client(lambda request: next(replies), max_retries=2).generate_json("s", "u", {})

    assert result.model_version == "gemini-test-001"
    assert SLEEPS == [38.0]


def test_streaming_retries_before_the_first_token_only() -> None:
    event = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, text=f"data: {json.dumps(event)}\r\n\r\n")

    pieces = list(client(handler, max_retries=2).stream_text("s", "u"))

    assert pieces == ["hello"]
    assert len(calls) == 2
    assert SLEEPS == [4.0]


def test_retries_stop_after_the_limit() -> None:
    with pytest.raises(LLMError, match="HTTP 429"):
        client(lambda request: httpx.Response(429, json=QUOTA), max_retries=3).generate_json(
            "s", "u", {}
        )

    assert len(SLEEPS) == 3
