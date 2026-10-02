"""Locate model-supplied quotes in the source text.

Models are unreliable at counting characters, so they are never asked for offsets.
They return a verbatim quote; the offsets are computed here, against the real text.
A quote that cannot be found is treated as fabricated.
"""

import re
from dataclasses import dataclass

_QUOTE_CLASSES = {
    "'": "['‘’]",
    "‘": "['‘’]",
    "’": "['‘’]",
    '"': '["“”]',
    "“": '["“”]',
    "”": '["“”]',
    "-": "[-‐‑–—]",
    "–": "[-‐‑–—]",
    "—": "[-‐‑–—]",
}


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    # False when the match needed whitespace or punctuation-style tolerance.
    exact: bool


def _tolerant_pattern(fragment: str) -> re.Pattern[str]:
    tokens = fragment.split()
    escaped = ["".join(_QUOTE_CLASSES.get(char, re.escape(char)) for char in t) for t in tokens]
    return re.compile(r"\s+".join(escaped), re.IGNORECASE)


def locate(text: str, fragment: str, *, start: int = 0, end: int | None = None) -> Span | None:
    """Find `fragment` in `text[start:end]`; offsets are relative to `text`."""
    fragment = fragment.strip()
    if not fragment:
        return None
    end = len(text) if end is None else end
    index = text.find(fragment, start, end)
    if index != -1:
        return Span(index, index + len(fragment), exact=True)
    match = _tolerant_pattern(fragment).search(text, start, end)
    if match is None:
        return None
    return Span(match.start(), match.end(), exact=False)
