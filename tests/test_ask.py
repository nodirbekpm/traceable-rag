import json
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.answer import AskConfig, ask, ask_stream
from anchor.api.main import app, get_ask_components, get_session_factory
from anchor.cache import MemoryCache
from anchor.config import Settings
from anchor.indexing import index_document
from anchor.models import QueryLog, SourceDocument
from anchor.rerank import NoReranker
from anchor.retrieval import retrieve
from anchor.storage import RawStore
from anchor.text import html_to_text
from embed_fakes import FakeEmbedder
from llm_fakes import FakeStreamingLLM

RESULTS_HTML = (
    b"<p>Item 2.02 Results of Operations and Financial Condition.</p>"
    b"<p>Example Corp reported revenue of $4.2 million for the quarter ended March 31, 2026.</p>"
    b"<p>Item 9.01 Financial Statements and Exhibits.</p><p>99.1 Press release.</p>"
)
OFFICER_HTML = (
    b"<p>Item 5.02 Departure of Directors or Certain Officers.</p>"
    b"<p>Jane Roe was appointed Chief Financial Officer effective June 1, 2026.</p>"
)

GOOD = {"claim": "Revenue was $4.2 million.", "source": "S1", "quote": "revenue of $4.2 million"}
INVENTED = {"claim": "Net income was $1.1 million.", "source": "S1", "quote": "net income $1.1M"}


def ndjson(*lines: dict) -> str:
    return "".join(json.dumps(line) + "\n" for line in lines)


@pytest.fixture
def corpus(session: Session, tmp_path: Path) -> dict[str, SourceDocument]:
    store = RawStore(tmp_path)
    documents = {}
    for name, html, filed in [
        ("results", RESULTS_HTML, datetime(2026, 5, 1, tzinfo=UTC)),
        ("officer", OFFICER_HTML, datetime(2026, 5, 20, tzinfo=UTC)),
    ]:
        blob = store.put(html)
        document = SourceDocument(
            source_url=f"https://www.sec.gov/{name}.htm",
            external_id=name,
            doc_type="8-K",
            publisher="Example Corp",
            published_at=filed,
            content_hash=blob.content_hash,
            raw_path=blob.relative_path,
        )
        session.add(document)
        session.commit()
        index_document(session, document, store, FakeEmbedder(), ("section",))
        documents[name] = document
    return documents


def components(answer: str, cache: MemoryCache | None = None) -> dict:
    return {
        "embedder": FakeEmbedder(),
        "reranker": NoReranker(),
        "llm": FakeStreamingLLM(answer),
        "cache": cache or MemoryCache(),
        "settings": Settings(),
    }


def test_text_search_finds_exact_amounts_and_item_numbers(session, corpus) -> None:
    hits = retrieve(session, FakeEmbedder(), "revenue $4.2 million", mode="text", k=3)

    assert hits[0].external_id == "results"
    assert hits[0].section == "2.02"
    assert "revenue of $4.2 million" in hits[0].text


@pytest.mark.parametrize("mode", ["vector", "text", "hybrid"])
def test_every_mode_returns_exact_document_slices(session, corpus, mode) -> None:
    hits = retrieve(session, FakeEmbedder(), "Who was appointed officer?", mode=mode, k=5)

    assert hits
    for found in hits:
        document = corpus[found.external_id]
        text = html_to_text(RESULTS_HTML if found.external_id == "results" else OFFICER_HTML)
        assert text[found.span_start : found.span_end] == found.text
        assert document.id == found.document_id


def test_hybrid_contains_the_keyword_match(session, corpus) -> None:
    hits = retrieve(session, FakeEmbedder(), "appointed Chief Financial Officer", k=2)

    assert any("Jane Roe" in found.text for found in hits)


def test_supported_claims_stream_with_document_offsets(session, corpus) -> None:
    parts = components(ndjson(GOOD, INVENTED))

    events = list(ask_stream(session, "What was revenue?", config=AskConfig(mode="text"), **parts))

    kinds = [event["event"] for event in events]
    assert kinds == ["sources", "claim", "done"]
    citation = events[1]["citation"]
    text = html_to_text(RESULTS_HTML)
    assert text[citation["span_start"] : citation["span_end"]] == "revenue of $4.2 million"
    assert citation["external_id"] == "results"
    done = events[-1]
    assert (done["claims"], done["claims_dropped"], done["not_found"]) == (1, 1, False)
    assert done["cost_usd"] == "0.00085"


def test_model_refusal_becomes_not_found(session, corpus) -> None:
    result = ask(
        session, "What is the CEO's favourite colour?", **components(ndjson({"not_found": True}))
    )

    assert result["not_found"] is True
    assert result["model_said_not_found"] is True
    assert result["answer"] == "Not found in the indexed documents."


def test_answer_whose_claims_all_fail_verification_is_not_found(session, corpus) -> None:
    result = ask(session, "What was net income?", **components(ndjson(INVENTED)))

    assert result["not_found"] is True
    assert result["model_said_not_found"] is False
    assert result["claims_dropped"] == 1


def test_prose_and_code_fences_around_the_json_lines_are_ignored(session, corpus) -> None:
    answer = "Here you go:\n```json\n" + ndjson(GOOD) + "```\n"

    result = ask(session, "What was revenue?", config=AskConfig(mode="text"), **components(answer))

    assert result["claims"][0]["text"] == "Revenue was $4.2 million."


def test_second_identical_question_is_served_from_cache(session, corpus) -> None:
    cache = MemoryCache()
    first_parts = components(ndjson(GOOD), cache)
    first = ask(session, "What was revenue?", **first_parts)
    second_parts = components(ndjson(GOOD), cache)

    second = ask(session, "  what was REVENUE? ", **second_parts)

    assert second["cache_hit"] is True
    assert second_parts["llm"].calls == []
    assert second["answer"] == first["answer"]
    logs = session.scalars(select(QueryLog).order_by(QueryLog.cache_hit)).all()
    assert [log.cache_hit for log in logs] == [False, True]
    assert logs[0].latency_ttft_ms is not None
    assert logs[1].cost_usd == 0


def test_query_log_records_stages_sources_and_citations(session, corpus) -> None:
    ask(session, "What was revenue?", config=AskConfig(mode="text"), **components(ndjson(GOOD)))

    log = session.scalar(select(QueryLog))
    assert log.config["mode"] == "text"
    assert log.config["reranker"] == "none"
    assert log.retrieved_chunk_ids
    assert log.citations[0]["quote"] == "revenue of $4.2 million"
    assert log.latency_retrieval_ms is not None
    assert log.latency_total_ms >= log.latency_retrieval_ms
    assert log.not_found is False


def test_ask_endpoint_streams_server_sent_events(session, corpus) -> None:
    app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(session)
    app.dependency_overrides[get_ask_components] = lambda: components(ndjson(GOOD))
    try:
        with TestClient(app) as client:
            response = client.get("/ask", params={"q": "What was revenue?", "mode": "text"})
    finally:
        app.dependency_overrides.clear()

    assert response.headers["content-type"].startswith("text/event-stream")
    names = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert names == ["sources", "claim", "done"]
