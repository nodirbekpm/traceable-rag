"""LLM access behind one small interface, so the provider is a configuration choice."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

from anchor.config import Settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


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


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise LLMError("GEMINI_API_KEY is not set.")
        self.model_name = model_name
        self._http = httpx.Client(
            headers={"x-goog-api-key": api_key}, transport=transport, timeout=120.0
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
        try:
            response = self._http.post(url, json=body)
        except httpx.TransportError as exc:
            raise LLMError(f"Gemini request failed: {exc!r}") from exc
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
