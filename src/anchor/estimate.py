"""How long and how much an analysis will take, before anyone commits to it.

Rates come from this installation's own history where possible: past extraction
runs give seconds per thousand input tokens, and the embedding rate is a
measured setting. A fresh install falls back to conservative defaults.
"""

import math
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anchor.chunking import chunk_section_aware
from anchor.config import Settings
from anchor.extraction.extractor import MAX_DOCUMENT_CHARS, windows
from anchor.models import ExtractionRun

CHARS_PER_TOKEN = 4
PROMPT_TOKENS = 900  # system prompt and field list sent with every window
OUTPUT_PER_INPUT = 0.8  # output incl. reasoning tokens, from observed runs
DEFAULT_SECONDS_PER_1K_INPUT = 3.0
WORDS_PER_PAGE = 500


@dataclass
class Estimate:
    characters: int
    words: int
    pages: int
    model_calls: int
    chunks: int
    seconds: int
    cost_usd: float
    truncated: bool
    basis: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def seconds_per_1k_input(session: Session) -> tuple[float, str]:
    """Measured from finished runs on this installation, or a default."""
    row = session.execute(
        select(
            func.count(),
            func.sum(func.extract("epoch", ExtractionRun.finished_at - ExtractionRun.started_at)),
            func.sum(ExtractionRun.token_input),
        ).where(
            ExtractionRun.status == "succeeded",
            ExtractionRun.finished_at.isnot(None),
            ExtractionRun.token_input > 0,
        )
    ).one()
    runs, seconds, tokens = row
    if runs and runs >= 3 and seconds and tokens:
        return float(seconds) / (float(tokens) / 1000), f"measured from {runs} earlier runs"
    return DEFAULT_SECONDS_PER_1K_INPUT, "default rates (no history yet)"


def estimate_analysis(
    session: Session, text: str, settings: Settings, *, pages: int | None = None
) -> Estimate:
    truncated = len(text) > MAX_DOCUMENT_CHARS
    text = text[:MAX_DOCUMENT_CHARS]
    words = len(text.split())
    pieces = windows(text)
    calls = len(pieces)
    input_tokens = len(text) / CHARS_PER_TOKEN + PROMPT_TOKENS * calls
    output_tokens = input_tokens * OUTPUT_PER_INPUT
    per_1k, basis = seconds_per_1k_input(session)
    extraction_s = per_1k * input_tokens / 1000
    # The free tier allows a few requests a minute; beyond that the client waits.
    waits = max(0, math.ceil(calls / settings.llm_requests_per_minute) - 1) * 60
    chunks = len(chunk_section_aware(text))
    embedding_s = chunks / settings.embedding_chunks_per_second
    cost = (
        Decimal(input_tokens) * settings.llm_price_input_per_mtok
        + Decimal(output_tokens) * settings.llm_price_output_per_mtok
    ) / Decimal(1_000_000)

    notes = []
    if truncated:
        notes.append(
            f"Only the first {MAX_DOCUMENT_CHARS:,} characters (about "
            f"{MAX_DOCUMENT_CHARS // (WORDS_PER_PAGE * 6)} pages) will be analysed."
        )
    if calls > 1:
        notes.append(f"The document is read in {calls} parts.")
    if waits:
        notes.append(f"About {waits} s of this is waiting for the model's rate limit.")
    return Estimate(
        characters=len(text),
        words=words,
        pages=pages or max(1, math.ceil(words / WORDS_PER_PAGE)),
        model_calls=calls,
        chunks=chunks,
        seconds=math.ceil(extraction_s + waits + embedding_s + 2),
        cost_usd=round(float(cost), 4),
        truncated=truncated,
        basis=basis,
        notes=notes,
    )
