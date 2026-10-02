import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.config import Settings
from anchor.extraction.extractor import extract_document, parse_facts
from anchor.llm import LLMError, LLMResult
from anchor.models import ExtractedFact, SourceDocument
from anchor.storage import RawStore
from anchor.text import html_to_text

HTML = (
    b"<html><body><p>Item 2.02 Results of Operations and Financial Condition.</p>"
    b"<p>On May 1, 2026, Example Corp reported revenue of $4.2&nbsp;million for the quarter.</p>"
    b"</body></html>"
)

GOOD = {
    "field": "revenue",
    "value": "$4.2 million",
    "quote": "reported revenue of $4.2 million for the quarter",
    "entity": None,
    "confidence": 0.9,
}
INVENTED = {
    "field": "net_income",
    "value": "$1.1 million",
    "quote": "net income of $1.1 million",
    "entity": None,
    "confidence": 0.99,
}


class FakeLLM:
    model_name = "fake-model"

    def __init__(self, facts: list[dict[str, Any]] | None = None, *, raw: str | None = None):
        self.raw = raw if raw is not None else json.dumps({"facts": facts or []})
        self.error: Exception | None = None
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        self.calls.append((system, user, schema))
        if self.error is not None:
            raise self.error
        return LLMResult(self.raw, input_tokens=1000, output_tokens=200, model_version="fake-001")


@pytest.fixture
def document(session: Session, tmp_path: Path) -> tuple[SourceDocument, RawStore]:
    store = RawStore(tmp_path)
    blob = store.put(HTML)
    document = SourceDocument(
        source_url="https://www.sec.gov/x.htm",
        external_id="0000000001-26-000001",
        doc_type="8-K",
        publisher="Example Corp",
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    return document, store


def facts_of(session: Session, run_id) -> dict[str, ExtractedFact]:
    rows = session.scalars(select(ExtractedFact).where(ExtractedFact.run_id == run_id))
    return {row.field_name: row for row in rows}


def test_verified_fact_is_stored_with_a_span_that_points_at_the_value(
    session: Session, document: tuple[SourceDocument, RawStore]
) -> None:
    doc, store = document

    run = extract_document(session, doc, FakeLLM([GOOD]), store, Settings())

    fact = facts_of(session, run.id)["revenue"]
    text = html_to_text(HTML)
    assert fact.validation_status == "verified"
    assert text[fact.span_start : fact.span_end] == "$4.2 million"
    assert fact.value_normalized == "4200000"
    assert fact.is_current is True


def test_invented_fact_is_kept_as_hallucinated_and_never_verified(
    session: Session, document: tuple[SourceDocument, RawStore]
) -> None:
    doc, store = document

    run = extract_document(session, doc, FakeLLM([GOOD, INVENTED]), store, Settings())

    facts = facts_of(session, run.id)
    assert facts["revenue"].validation_status == "verified"
    assert facts["net_income"].validation_status == "hallucinated"
    assert facts["net_income"].validation_reason == "quote not found in source"
    assert facts["net_income"].span_start is None


def test_run_records_versions_tokens_and_list_price_cost(
    session: Session, document: tuple[SourceDocument, RawStore]
) -> None:
    doc, store = document
    llm = FakeLLM([GOOD])

    run = extract_document(session, doc, llm, store, Settings())

    assert run.status == "succeeded"
    assert (run.model_name, run.model_version) == ("fake-model", "fake-001")
    assert (run.prompt_version, run.schema_version, run.text_version) == ("p1", "s1", "t1")
    assert (run.token_input, run.token_output) == (1000, 200)
    # 1000 * $0.30/M + 200 * $2.50/M
    assert run.cost_usd == Decimal("0.0008")
    assert run.finished_at is not None
    assert "$4.2 million" in llm.calls[0][1]
    assert "facts" in llm.calls[0][2]["properties"]


def test_provider_failure_marks_the_run_failed_and_stores_no_facts(
    session: Session, document: tuple[SourceDocument, RawStore]
) -> None:
    doc, store = document
    llm = FakeLLM()
    llm.error = LLMError("HTTP 429")

    run = extract_document(session, doc, llm, store, Settings())

    assert run.status == "failed"
    assert facts_of(session, run.id) == {}


def test_unparseable_model_output_marks_the_run_failed(
    session: Session, document: tuple[SourceDocument, RawStore]
) -> None:
    doc, store = document

    run = extract_document(
        session, doc, FakeLLM(raw="Sure! Here are the facts:"), store, Settings()
    )

    assert run.status == "failed"
    assert run.token_input == 1000


def test_one_malformed_fact_does_not_discard_the_others() -> None:
    payload = json.dumps({"facts": [GOOD, {"field": "made_up_field", "value": "x"}, "junk"]})

    facts, dropped = parse_facts(payload)

    assert [f.field for f in facts] == ["revenue"]
    assert dropped == 2


def test_output_without_a_facts_list_is_an_error() -> None:
    with pytest.raises(ValueError, match="facts"):
        parse_facts('{"result": []}')
