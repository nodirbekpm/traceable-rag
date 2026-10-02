"""Decide what a model-returned fact is worth.

Order matters: provenance first. A value that is not in the source is a
hallucination no matter how well-formed it looks.
"""

from dataclasses import dataclass
from decimal import Decimal

from anchor.extraction.normalize import NormalizationError, normalize
from anchor.extraction.provenance import locate
from anchor.extraction.schema import FIELDS, FactOut, Kind

REVIEW_THRESHOLD = 0.7
# Applied when the quote matched only after whitespace/punctuation tolerance.
INEXACT_MATCH_PENALTY = 0.9

# Sanity bounds; values outside them are almost certainly a unit or parsing mistake.
_MAX_MONEY = Decimal(10) ** 13
_MAX_PER_SHARE = Decimal(100_000)
_MAX_PERCENT = Decimal(10_000)


@dataclass(frozen=True)
class ValidatedFact:
    field_name: str
    entity_id: str | None
    value_raw: str
    value_normalized: str | None
    unit: str | None
    span_start: int | None
    span_end: int | None
    source_excerpt: str | None
    confidence: float
    validation_status: str
    reason: str | None = None


def _in_range(kind: Kind, normalized: str) -> bool:
    if kind is Kind.MONEY:
        return abs(Decimal(normalized)) <= _MAX_MONEY
    if kind is Kind.PER_SHARE:
        return abs(Decimal(normalized)) <= _MAX_PER_SHARE
    if kind is Kind.PERCENT:
        return abs(Decimal(normalized)) <= _MAX_PERCENT
    if kind is Kind.DATE:
        return "1990-01-01" <= normalized <= "2100-01-01"
    return True


def validate(fact: FactOut, text: str) -> ValidatedFact:
    kind = FIELDS[fact.field][0]
    value_raw = " ".join(fact.value.split())

    def result(status: str, reason: str | None = None, **fields) -> ValidatedFact:
        base = {
            "field_name": fact.field,
            "entity_id": fact.entity,
            "value_raw": value_raw,
            "value_normalized": None,
            "unit": None,
            "span_start": None,
            "span_end": None,
            "source_excerpt": None,
            "confidence": 0.0,
        }
        return ValidatedFact(**(base | fields), validation_status=status, reason=reason)

    quote = locate(text, fact.quote)
    if quote is None:
        return result("hallucinated", "quote not found in source")
    excerpt = text[quote.start : quote.end]
    value = locate(text, value_raw, start=quote.start, end=quote.end)
    if value is None:
        return result("hallucinated", "value not found inside its quote", source_excerpt=excerpt)

    located = {"span_start": value.start, "span_end": value.end, "source_excerpt": excerpt}
    try:
        normalized = normalize(kind, value_raw)
    except NormalizationError as exc:
        return result("rejected", str(exc), **located)
    located |= {"value_normalized": normalized.value, "unit": normalized.unit}
    if not _in_range(kind, normalized.value):
        return result("rejected", "value outside the plausible range", **located)

    confidence = fact.confidence
    if not (quote.exact and value.exact):
        confidence *= INEXACT_MATCH_PENALTY
    located["confidence"] = round(confidence, 3)
    if confidence < REVIEW_THRESHOLD:
        return result("needs_review", "confidence below threshold", **located)
    return result("verified", **located)
