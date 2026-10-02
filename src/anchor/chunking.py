"""Three chunking strategies over the canonical text.

Invariant shared by all of them: `chunk.text == text[chunk.span_start:chunk.span_end]`.
A chunk is always an exact slice of the source, so anything retrieved can be
traced back to the document without guessing.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

FIXED_SIZE = 800
FIXED_OVERLAP = 120
SENTENCE_MAX_CHARS = 800
SECTION_MAX_CHARS = 1200

_SENTENCE_END = re.compile(r"(?<=[.!?])[\"”’)]*\s+(?=[A-Z0-9“\"(])|\n{2,}")
_PARAGRAPH_BREAK = re.compile(r"\n{2,}")
_ITEM_HEADING = re.compile(r"^Item\s+(\d\.\d{2})\b", re.MULTILINE)
_SIGNATURE_HEADING = re.compile(r"^SIGNATURES?\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    span_start: int
    span_end: int
    text: str
    # "2.02" for an Item section, "preamble" / "signature" otherwise; None when
    # the strategy does not know about sections.
    section: str | None = None


Span = tuple[int, int]


def _trim(text: str, start: int, end: int) -> Span | None:
    """Shrink a span so it does not begin or end with whitespace."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if start < end else None


def _number(text: str, spans: Iterator[tuple[int, int, str | None]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for start, end, section in spans:
        trimmed = _trim(text, start, end)
        if trimmed is None:
            continue
        chunks.append(
            Chunk(len(chunks), trimmed[0], trimmed[1], text[trimmed[0] : trimmed[1]], section)
        )
    return chunks


def _fixed_spans(start: int, end: int, size: int, overlap: int) -> Iterator[Span]:
    step = size - overlap
    position = start
    while position < end:
        yield position, min(position + size, end)
        if position + size >= end:
            break
        position += step


def _split(text: str, start: int, end: int, boundary: re.Pattern[str]) -> list[Span]:
    spans: list[Span] = []
    position = start
    for match in boundary.finditer(text, start, end):
        spans.append((position, match.start()))
        position = match.end()
    spans.append((position, end))
    return [span for span in spans if _trim(text, *span) is not None]


def _pack(units: list[Span], max_chars: int, *, overlap_units: int = 0) -> list[Span]:
    """Group consecutive units into spans of at most `max_chars`, where possible."""
    packed: list[Span] = []
    index = 0
    while index < len(units):
        first = index
        last = index
        while last + 1 < len(units) and units[last + 1][1] - units[first][0] <= max_chars:
            last += 1
        packed.append((units[first][0], units[last][1]))
        if last + 1 >= len(units):
            break
        # Step back to repeat the tail of this group, but always make progress.
        index = max(last + 1 - overlap_units, first + 1)
    return packed


def chunk_fixed(text: str, size: int = FIXED_SIZE, overlap: int = FIXED_OVERLAP) -> list[Chunk]:
    """Baseline: fixed-size character windows with overlap, blind to structure."""
    return _number(text, ((s, e, None) for s, e in _fixed_spans(0, len(text), size, overlap)))


def chunk_sentence_window(text: str, max_chars: int = SENTENCE_MAX_CHARS) -> list[Chunk]:
    """Whole sentences packed up to `max_chars`; neighbours share one sentence."""
    sentences = _split(text, 0, len(text), _SENTENCE_END)
    return _number(text, ((s, e, None) for s, e in _pack(sentences, max_chars, overlap_units=1)))


def _sections(text: str) -> list[tuple[int, int, str]]:
    marks: list[tuple[int, str]] = [(m.start(), m.group(1)) for m in _ITEM_HEADING.finditer(text)]
    signature = None
    for match in _SIGNATURE_HEADING.finditer(text):
        signature = match.start()
    if signature is not None and (not marks or signature > marks[-1][0]):
        marks.append((signature, "signature"))
    if not marks or marks[0][0] > 0:
        marks.insert(0, (0, "preamble"))
    ends = [start for start, _ in marks[1:]] + [len(text)]
    return [(start, end, label) for (start, label), end in zip(marks, ends, strict=True)]


def chunk_section_aware(text: str, max_chars: int = SECTION_MAX_CHARS) -> list[Chunk]:
    """Never crosses an `Item` boundary; long sections split at paragraphs, then sentences."""

    def spans() -> Iterator[tuple[int, int, str | None]]:
        for start, end, label in _sections(text):
            if end - start <= max_chars:
                yield start, end, label
                continue
            units: list[Span] = []
            for p_start, p_end in _split(text, start, end, _PARAGRAPH_BREAK):
                if p_end - p_start <= max_chars:
                    units.append((p_start, p_end))
                    continue
                for s_start, s_end in _split(text, p_start, p_end, _SENTENCE_END):
                    if s_end - s_start <= max_chars:
                        units.append((s_start, s_end))
                    else:
                        units.extend(_fixed_spans(s_start, s_end, max_chars, 0))
            for c_start, c_end in _pack(units, max_chars):
                yield c_start, c_end, label

    return _number(text, spans())


STRATEGIES: dict[str, Callable[[str], list[Chunk]]] = {
    "fixed": chunk_fixed,
    "sentence": chunk_sentence_window,
    "section": chunk_section_aware,
}
