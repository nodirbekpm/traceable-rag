"""LLM access behind one small interface, so the provider is a configuration choice."""

import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

from anchor.config import Settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_STREAM_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
)


# Rate limits and overload are temporary; anything else is reported at once.
RETRYABLE_STATUS = {429, 500, 503}


class LLMError(RuntimeError):
    pass


# Never wait longer than this for one retry: a longer hint means the quota is gone
# for hours, and the caller should hear that instead of a silent hang.
MAX_RETRY_DELAY_SECONDS = 120.0


def _details(response: httpx.Response) -> list[dict]:
    try:
        return list(response.json()["error"].get("details", []))
    except (ValueError, KeyError, TypeError, AttributeError):
        return []


def daily_quota_exhausted(response: httpx.Response) -> bool:
    """True when a 429 names a per-day quota, which no short wait will fix."""
    return response.status_code == 429 and any(
        "perday" in str(violation.get("quotaId", "")).lower()
        for detail in _details(response)
        for violation in detail.get("violations", [])
    )


def retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait: the provider's RetryInfo hint when given, else exponential backoff."""
    for detail in _details(response):
        if match := re.fullmatch(r"([\d.]+)s", str(detail.get("retryDelay", ""))):
            return min(float(match.group(1)) + 1, MAX_RETRY_DELAY_SECONDS)
    return min(float(2 ** (attempt + 2)), MAX_RETRY_DELAY_SECONDS)


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    # The exact model build that answered, as reported by the provider.
    model_version: str


class LLMClient(Protocol):
    model_name: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult: ...

    def stream_text(self, system: str, user: str) -> Iterator[str]:
        """Yield text as it is generated. After exhaustion `last_usage` holds token counts."""
        ...

    @property
    def last_usage(self) -> LLMResult | None: ...


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 4,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise LLMError("GEMINI_API_KEY is not set.")
        self.model_name = model_name
        self._http = httpx.Client(
            headers={"x-goog-api-key": api_key}, transport=transport, timeout=120.0
        )
        self._last_usage: LLMResult | None = None
        self._max_retries = max_retries
        self._sleep = sleep

    def _should_retry(self, response: httpx.Response, attempt: int) -> bool:
        if response.status_code not in RETRYABLE_STATUS or attempt >= self._max_retries:
            return False
        if daily_quota_exhausted(response):
            raise LLMError(
                "The model's daily free-tier quota is used up; it resets once a day. "
                "Try again later or use a paid key."
            )
        self._sleep(retry_delay(response, attempt))
        return True

    @property
    def last_usage(self) -> LLMResult | None:
        return self._last_usage

    def stream_text(self, system: str, user: str) -> Iterator[str]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0},
        }
        self._last_usage = None
        usage: dict[str, Any] = {}
        model_version = self.model_name
        produced: list[str] = []
        url = GEMINI_STREAM_URL.format(model=self.model_name)
        try:
            for attempt in range(self._max_retries + 1):
                with self._http.stream("POST", url, json=body) as response:
                    if response.is_error:
                        response.read()
                        if self._should_retry(response, attempt):
                            continue
                        raise LLMError(
                            f"Gemini returned HTTP {response.status_code}: {response.text[:300]}"
                        )
                    # Retries only happen before the first token, so nothing is yielded twice.
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:])
                        usage = event.get("usageMetadata", usage)
                        model_version = event.get("modelVersion", model_version)
                        for candidate in event.get("candidates", [])[:1]:
                            for part in candidate.get("content", {}).get("parts", []):
                                if part.get("text") and not part.get("thought"):
                                    produced.append(part["text"])
                                    yield part["text"]
                    break
        except httpx.TransportError as exc:
            raise LLMError(f"Gemini request failed: {exc!r}") from exc
        output_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        self._last_usage = LLMResult(
            text="".join(produced),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=output_tokens,
            model_version=model_version,
        )

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        url = GEMINI_URL.format(model=self.model_name)
        attempt = 0
        while True:
            try:
                response = self._http.post(url, json=body)
            except httpx.TransportError as exc:
                raise LLMError(f"Gemini request failed: {exc!r}") from exc
            if not self._should_retry(response, attempt):
                break
            attempt += 1
        if response.is_error:
            raise LLMError(f"Gemini returned HTTP {response.status_code}: {response.text[:300]}")
        payload = response.json()
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError) as exc:
            reason = payload.get("promptFeedback") or payload.get("candidates")
            raise LLMError(f"Gemini returned no content: {reason}") from exc
        usage = payload.get("usageMetadata", {})
        output_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
        return LLMResult(
            text=text,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=output_tokens,
            model_version=payload.get("modelVersion", self.model_name),
        )


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "gemini":
        return GeminiClient(settings.gemini_api_key, settings.llm_model)
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")


def cost_usd(result: LLMResult, settings: Settings) -> Decimal:
    """List-price cost of a call, even when it ran on a free tier, so runs stay comparable."""
    million = Decimal(1_000_000)
    return (
        Decimal(result.input_tokens) * settings.llm_price_input_per_mtok
        + Decimal(result.output_tokens) * settings.llm_price_output_per_mtok
    ) / million
