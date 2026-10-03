import uuid
from datetime import UTC, datetime

from anchor.answer import AskConfig, _lines, build_context, cache_key, verify_claim
from anchor.cache import MemoryCache
from anchor.retrieval import Hit, reciprocal_rank_fusion

TEXT = "Item 2.02. Example Corp reported revenue of $4.2 million, up 12% from $3.75 million."


def hit(text: str = TEXT, *, span_start: int = 1000, superseded: bool = False, **kw) -> Hit:
    fields = {
        "chunk_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "text": text,
        "span_start": span_start,
        "span_end": span_start + len(text),
        "section": "2.02",
        "doc_type": "8-K",
        "external_id": "0000000001-26-000001",
        "publisher": "Example Corp",
        "published_at": datetime(2026, 5, 1, tzinfo=UTC),
        "score": 1.0,
        "superseded": superseded,
    }
    return Hit(**(fields | kw))


def claim(**overrides) -> dict:
    base = {
        "claim": "Revenue was $4.2 million.",
        "source": "S1",
        "quote": "reported revenue of $4.2 million",
    }
    return base | overrides


def test_supported_claim_gets_document_offsets() -> None:
    source = hit()

    citation = verify_claim(claim(), {"S1": source})

    local = TEXT.index("reported revenue of $4.2 million")
    assert citation.span_start == 1000 + local
    assert citation.span_end - citation.span_start == len("reported revenue of $4.2 million")
    assert citation.quote == "reported revenue of $4.2 million"
    assert citation.chunk_id == str(source.chunk_id)


def test_claim_citing_an_unknown_source_is_dropped() -> None:
    assert verify_claim(claim(source="S9"), {"S1": hit()}) == "unknown source 'S9'"


def test_claim_whose_quote_is_not_in_the_source_is_dropped() -> None:
    reason = verify_claim(claim(quote="revenue of $5 million"), {"S1": hit()})

    assert reason == "quote not found in source"


def test_claim_with_a_number_missing_from_its_quote_is_dropped() -> None:
    wrong = claim(claim="Revenue was $4.2 million, up 15%.")

    assert verify_claim(wrong, {"S1": hit()}) == "claim states a number its quote does not contain"


def test_numbers_match_regardless_of_thousands_separators() -> None:
    text = "Total consideration was 4,200,000 shares."
    supported = claim(claim="The consideration was 4200000 shares.", quote=text)

    assert not isinstance(verify_claim(supported, {"S1": hit(text)}), str)


def test_malformed_claim_is_dropped() -> None:
    assert verify_claim({"claim": "", "source": "S1", "quote": "x"}, {"S1": hit()}) == (
        "malformed claim"
    )


def test_context_labels_sources_and_flags_superseded_ones() -> None:
    context, sources = build_context([hit(), hit("Older text.", superseded=True, section=None)])

    assert list(sources) == ["S1", "S2"]
    assert "[S1] Example Corp, 8-K filed 2026-05-01, Item 2.02\n" in context
    assert "[S2] Example Corp, 8-K filed 2026-05-01 [SUPERSEDED]\nOlder text." in context


def test_lines_are_reassembled_from_arbitrary_pieces() -> None:
    pieces = iter(['{"a"', ': 1}\n{"b": 2', "}\n", '{"c": 3}'])

    assert list(_lines(pieces)) == ['{"a": 1}', '{"b": 2}', '{"c": 3}']


def test_cache_key_changes_with_config_components_and_corpus() -> None:
    components = {"llm": "m", "prompt": "a1"}
    base = cache_key("What was revenue?", AskConfig(), components, "5:95")

    assert base == cache_key("  what was   REVENUE? ", AskConfig(), components, "5:95")
    assert base != cache_key("What was revenue?", AskConfig(mode="text"), components, "5:95")
    assert base != cache_key("What was revenue?", AskConfig(), components | {"llm": "x"}, "5:95")
    assert base != cache_key("What was revenue?", AskConfig(), components, "6:120")


def test_memory_cache_round_trip() -> None:
    cache = MemoryCache()

    cache.set("k", [{"event": "done"}])

    assert cache.get("k") == [{"event": "done"}]
    assert cache.get("missing") is None


def test_rrf_rewards_chunks_found_by_both_searches() -> None:
    a, b, c = hit("a"), hit("b"), hit("c")

    fused = reciprocal_rank_fusion([[a, b], [c, b]], k=3)

    assert fused[0].chunk_id == b.chunk_id
    assert {h.chunk_id for h in fused} == {a.chunk_id, b.chunk_id, c.chunk_id}
    assert fused[0].score == 1 / 62 + 1 / 62
