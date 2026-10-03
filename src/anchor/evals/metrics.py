"""Pure scoring functions. No database, no model: everything here is unit-tested."""

import math
import re
from collections.abc import Iterable, Sequence

from anchor.extraction.provenance import locate
from anchor.extraction.schema import FIELDS, Kind

_TEXT_KINDS = {Kind.TEXT}


def occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    """Every place `quote` appears in `text` (with the same tolerance as the validator)."""
    found: list[tuple[int, int]] = []
    start = 0
    while (span := locate(text, quote, start=start)) is not None:
        found.append((span.start, span.end))
        start = span.start + 1
    return found


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _fold(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s.,%$-]", " ", value.casefold()).split()).strip(" .,")


def values_match(field: str, expected: str, actual: str | None) -> bool:
    """Exact match on normalized values; for free text, either one containing the other."""
    if actual is None:
        return False
    if FIELDS[field][0] in _TEXT_KINDS:
        a, b = _fold(expected), _fold(actual)
        return bool(a and b) and (a in b or b in a)
    return expected == actual


def contains_fact(answer: str, fact: str) -> bool:
    """Whether an answer states a key fact, ignoring case and thousands separators."""

    def norm(value: str) -> str:
        return re.sub(r"(?<=\d),(?=\d{3})", "", " ".join(value.casefold().split()))

    return norm(fact) in norm(answer)


def first_relevant_rank(hits: Sequence[bool]) -> int | None:
    return next((rank for rank, relevant in enumerate(hits, start=1) if relevant), None)


def recall_at(ranks: Iterable[int | None], k: int) -> float:
    ranks = list(ranks)
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0


def mean_reciprocal_rank(ranks: Iterable[int | None]) -> float:
    ranks = list(ranks)
    return sum(1 / r for r in ranks if r is not None) / len(ranks) if ranks else 0.0


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile; None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(math.ceil(q / 100 * len(ordered)) - 1, 0)
    return round(ordered[index], 1)


def ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None
