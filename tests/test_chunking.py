from itertools import pairwise

import pytest

from anchor.chunking import (
    STRATEGIES,
    chunk_fixed,
    chunk_section_aware,
    chunk_sentence_window,
)

PARAGRAPH = (
    "Example Corp reported revenue of $4.2 million for the quarter. "
    "Diluted earnings per share were $1.64. The board declared a dividend of $0.25 per share. "
)
DOCUMENT = (
    "UNITED STATES\nSECURITIES AND EXCHANGE COMMISSION\n\nFORM 8-K\n\n"
    "Item 2.02 Results of Operations and Financial Condition.\n\n"
    + "\n\n".join(PARAGRAPH * 3 for _ in range(4))
    + "\n\nItem 9.01 Financial Statements and Exhibits.\n\n(d) Exhibits. 99.1 Press release.\n\n"
    "SIGNATURE\n\nPursuant to the requirements of the Securities Exchange Act of 1934.\n\n"
    "Date: May 1, 2026"
)


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_every_chunk_is_an_exact_slice_of_the_source(strategy: str) -> None:
    chunks = STRATEGIES[strategy](DOCUMENT)

    assert chunks
    for chunk in chunks:
        assert chunk.text == DOCUMENT[chunk.span_start : chunk.span_end]
        assert chunk.text == chunk.text.strip()
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_no_part_of_the_document_is_lost(strategy: str) -> None:
    chunks = STRATEGIES[strategy](DOCUMENT)

    covered = [False] * len(DOCUMENT)
    for chunk in chunks:
        covered[chunk.span_start : chunk.span_end] = [True] * (chunk.span_end - chunk.span_start)
    missed = "".join(char for char, hit in zip(DOCUMENT, covered, strict=True) if not hit)
    assert missed.strip() == ""


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_empty_and_blank_documents_produce_no_chunks(strategy: str) -> None:
    assert STRATEGIES[strategy]("") == []
    assert STRATEGIES[strategy]("  \n\n ") == []


def test_fixed_windows_have_the_requested_size_and_overlap() -> None:
    text = "".join(str(i % 10) for i in range(250))

    chunks = chunk_fixed(text, size=100, overlap=20)

    assert [(c.span_start, c.span_end) for c in chunks] == [(0, 100), (80, 180), (160, 250)]


def test_sentence_windows_end_on_sentence_boundaries_and_share_one_sentence() -> None:
    chunks = chunk_sentence_window(PARAGRAPH * 4, max_chars=260)

    assert len(chunks) > 1
    assert all(chunk.text.endswith(".") for chunk in chunks)
    assert all(len(chunk.text) <= 260 for chunk in chunks)
    for left, right in pairwise(chunks):
        assert left.span_start < right.span_start < left.span_end


def test_sentence_longer_than_the_limit_is_kept_whole() -> None:
    long_sentence = "Revenue " + "increased " * 60 + "significantly."

    chunks = chunk_sentence_window(f"Short one. {long_sentence} Short two.", max_chars=100)

    assert long_sentence in [chunk.text for chunk in chunks]


def test_section_chunks_never_cross_an_item_boundary() -> None:
    chunks = chunk_section_aware(DOCUMENT, max_chars=600)

    assert [c.section for c in chunks if c.text.startswith("Item ")] == ["2.02", "9.01"]
    assert {c.section for c in chunks} == {"preamble", "2.02", "9.01", "signature"}
    for chunk in chunks:
        assert chunk.text.count("Item 2.02") + chunk.text.count("Item 9.01") <= 1
        assert len(chunk.text) <= 600
    results = [c for c in chunks if c.section == "2.02"]
    assert len(results) > 1
    assert "Item 9.01" not in "".join(c.text for c in results)


def test_short_sections_stay_in_one_chunk() -> None:
    chunks = chunk_section_aware(DOCUMENT, max_chars=600)

    exhibits = [c for c in chunks if c.section == "9.01"]
    assert len(exhibits) == 1
    assert exhibits[0].text.endswith("99.1 Press release.")


def test_document_without_items_is_one_preamble_section() -> None:
    chunks = chunk_section_aware("Just a short cover letter.")

    assert [(c.section, c.text) for c in chunks] == [("preamble", "Just a short cover letter.")]


def test_oversized_paragraph_without_sentences_falls_back_to_fixed_windows() -> None:
    blob = "Item 1.01 " + "x" * 2500

    chunks = chunk_section_aware(blob, max_chars=1000)

    assert all(len(c.text) <= 1000 for c in chunks)
    assert "".join(c.text for c in chunks) == blob
