from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anchor.api.main import app
from anchor.config import Settings
from anchor.db import get_session
from anchor.extraction import extractor
from anchor.extraction.extractor import extract_document
from anchor.extraction.versioning import fact_history
from anchor.llm import LLMError
from anchor.models import ExtractedFact, ExtractionRun, ReviewQueue, SourceDocument
from anchor.storage import RawStore
from llm_fakes import FakeLLM

ORIGINAL_HTML = (
    b"<p>Item 5.02 Departure of Directors or Certain Officers.</p>"
    b"<p>On April 20, 2026, Jane Roe was appointed Chief Financial Officer, "
    b"effective May 1, 2026, with a base salary of $900,000 USD.</p>"
)
AMENDMENT_HTML = (
    b"<p>This Amendment No. 1 amends the Current Report on Form 8-K filed on April 21, 2026.</p>"
    b"<p>Item 5.02. The appointment of Jane Roe will instead be effective June 15, 2026.</p>"
)


def fact(field: str, value: str, quote: str, confidence: float = 0.95, entity: str | None = None):
    return {
        "field": field,
        "value": value,
        "quote": quote,
        "entity": entity,
        "confidence": confidence,
    }


EFFECTIVE = fact(
    "officer_effective_date", "May 1, 2026", "effective May 1, 2026", entity="Jane Roe"
)
SALARY = fact("transaction_amount", "$900,000 USD", "a base salary of $900,000 USD")
AMENDED = fact(
    "officer_effective_date",
    "June 15, 2026",
    "will instead be effective June 15, 2026",
    entity="Jane Roe",
)


@pytest.fixture
def store(tmp_path: Path) -> RawStore:
    return RawStore(tmp_path)


def add_document(
    session: Session, store: RawStore, html: bytes, doc_type: str, published: datetime
) -> SourceDocument:
    blob = store.put(html)
    document = SourceDocument(
        source_url=f"https://www.sec.gov/{blob.content_hash[:8]}.htm",
        external_id=blob.content_hash[:20],
        doc_type=doc_type,
        publisher="Example Corp",
        publisher_id="1",
        published_at=published,
        content_hash=blob.content_hash,
        raw_path=blob.relative_path,
    )
    session.add(document)
    session.commit()
    return document


@pytest.fixture
def original(session: Session, store: RawStore) -> SourceDocument:
    return add_document(
        session, store, ORIGINAL_HTML, "8-K", datetime(2026, 4, 21, 20, 30, tzinfo=UTC)
    )


@pytest.fixture
def amendment(session: Session, store: RawStore) -> SourceDocument:
    return add_document(
        session, store, AMENDMENT_HTML, "8-K/A", datetime(2026, 9, 2, 20, 30, tzinfo=UTC)
    )


def facts(session: Session, document: SourceDocument) -> dict[str, list[ExtractedFact]]:
    rows = session.scalars(
        select(ExtractedFact)
        .where(ExtractedFact.document_id == document.id)
        .order_by(ExtractedFact.created_at, ExtractedFact.value_raw)
    )
    grouped: dict[str, list[ExtractedFact]] = {}
    for row in rows:
        grouped.setdefault(row.field_name, []).append(row)
    return grouped


def run(session, document, store, payload) -> ExtractionRun:
    return extract_document(session, document, FakeLLM(payload), store, Settings())


# --- idempotency ---------------------------------------------------------------


def test_same_document_and_versions_are_not_extracted_twice(session, original, store) -> None:
    first = run(session, original, store, [EFFECTIVE])
    llm = FakeLLM([EFFECTIVE])

    second = extract_document(session, original, llm, store, Settings())

    assert second.id == first.id
    assert llm.calls == []
    assert len(facts(session, original)["officer_effective_date"]) == 1


def test_database_refuses_a_second_successful_run_with_the_same_key(session, original) -> None:
    def new_run() -> ExtractionRun:
        return ExtractionRun(
            document_id=original.id,
            model_name="m",
            model_version="m-1",
            prompt_version="p1",
            schema_version="s1",
            text_version="t1",
            status="succeeded",
        )

    session.add(new_run())
    session.flush()
    session.add(new_run())

    with pytest.raises(IntegrityError, match="uq_extraction_run_version_key"):
        session.flush()


def test_failed_run_can_be_retried_and_does_not_retire_anything(session, original, store) -> None:
    run(session, original, store, [EFFECTIVE])
    failing = FakeLLM()
    failing.error = LLMError("HTTP 503")
    failing.model_name = "other-model"

    failed = extract_document(session, original, failing, store, Settings())
    retry_llm = FakeLLM([EFFECTIVE])
    retry_llm.model_name = "other-model"
    retried = extract_document(session, original, retry_llm, store, Settings())

    assert failed.status == "failed"
    assert retried.status == "succeeded"
    assert retried.id != failed.id


# --- versioning inside one document ---------------------------------------------


def test_new_prompt_version_adds_a_run_and_keeps_the_old_fact_as_history(
    session, original, store, monkeypatch
) -> None:
    run(session, original, store, [EFFECTIVE, SALARY])
    monkeypatch.setattr(extractor, "PROMPT_VERSION", "p2")
    corrected = EFFECTIVE | {"value": "April 20, 2026", "quote": "On April 20, 2026, Jane Roe"}

    second = run(session, original, store, [corrected])

    # Rows of one test share a transaction timestamp, so tell them apart by run.
    rows = facts(session, original)["officer_effective_date"]
    new = next(row for row in rows if row.run_id == second.id)
    old = next(row for row in rows if row.run_id != second.id)
    assert (old.is_current, new.is_current) == (False, True)
    assert old.superseded_by == new.id
    assert (old.value_normalized, new.value_normalized) == ("2026-05-01", "2026-04-20")
    assert new.run_id == second.id
    # The salary was not reported by the new run: it is history too, with no successor.
    salary = facts(session, original)["transaction_amount"][0]
    assert (salary.is_current, salary.superseded_by) == (False, None)
    assert session.scalar(select(ExtractionRun).where(ExtractionRun.prompt_version == "p1"))


def test_history_walks_back_through_every_replaced_value(
    session, original, store, monkeypatch
) -> None:
    run(session, original, store, [EFFECTIVE])
    monkeypatch.setattr(extractor, "PROMPT_VERSION", "p2")
    run(session, original, store, [EFFECTIVE])
    monkeypatch.setattr(extractor, "PROMPT_VERSION", "p3")
    run(session, original, store, [EFFECTIVE])

    rows = facts(session, original)["officer_effective_date"]
    current = next(row for row in rows if row.is_current)
    chain = fact_history(session, current.id)

    assert len(rows) == 3
    assert [row.is_current for row in chain] == [True, False, False]
    assert {row.id for row in chain} == {row.id for row in rows}


def test_repeated_fields_are_paired_by_value(session, original, store, monkeypatch) -> None:
    item = fact("item_number", "5.02", "Item 5.02 Departure of Directors")
    date = fact("report_date", "April 20, 2026", "On April 20, 2026, Jane Roe")
    other = fact("report_date", "May 1, 2026", "effective May 1, 2026")
    run(session, original, store, [item, date, other])
    monkeypatch.setattr(extractor, "PROMPT_VERSION", "p2")

    run(session, original, store, [item, date])

    old_dates = [f for f in facts(session, original)["report_date"] if not f.is_current]
    successors = {f.value_normalized: f.superseded_by for f in old_dates}
    assert successors["2026-04-20"] is not None
    assert successors["2026-05-01"] is None


# --- amendments -----------------------------------------------------------------


def test_amendment_is_linked_and_retires_only_the_facts_it_restates(
    session, original, amendment, store
) -> None:
    run(session, original, store, [EFFECTIVE, SALARY])

    run(session, amendment, store, [AMENDED])

    assert amendment.supersedes_id == original.id
    old = facts(session, original)
    new = facts(session, amendment)["officer_effective_date"][0]
    assert old["officer_effective_date"][0].is_current is False
    assert old["officer_effective_date"][0].superseded_by == new.id
    assert old["transaction_amount"][0].is_current is True
    assert [f.value_normalized for f in fact_history(session, new.id)] == [
        "2026-06-15",
        "2026-05-01",
    ]


def test_order_of_extraction_does_not_matter(session, original, amendment, store) -> None:
    run(session, amendment, store, [AMENDED])

    run(session, original, store, [EFFECTIVE, SALARY])

    old = facts(session, original)["officer_effective_date"][0]
    new = facts(session, amendment)["officer_effective_date"][0]
    assert (old.is_current, old.superseded_by) == (False, new.id)
    assert new.is_current is True


def test_unverified_amendment_fact_does_not_displace_a_verified_one(
    session, original, amendment, store
) -> None:
    run(session, original, store, [EFFECTIVE])
    invented = AMENDED | {"quote": "effective as of June 15, 2026 per the board"}

    run(session, amendment, store, [invented])

    assert (
        facts(session, amendment)["officer_effective_date"][0].validation_status == "hallucinated"
    )
    assert facts(session, original)["officer_effective_date"][0].is_current is True


def test_amendment_without_a_matching_filing_date_is_not_linked(session, amendment, store) -> None:
    add_document(session, store, ORIGINAL_HTML, "8-K", datetime(2026, 3, 3, 20, 30, tzinfo=UTC))

    run(session, amendment, store, [AMENDED])

    assert amendment.supersedes_id is None


# --- review queue and API ----------------------------------------------------------


@pytest.fixture
def client(session: Session):
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_low_confidence_fact_is_queued_and_can_be_accepted(
    session, original, store, client
) -> None:
    run(session, original, store, [EFFECTIVE | {"confidence": 0.4}])

    queued = client.get("/review").json()
    assert len(queued) == 1
    assert queued[0]["reason"] == "confidence below threshold"

    resolved = client.post(f"/review/{queued[0]['id']}/resolve", json={"accept": True})

    assert resolved.json()["resolution"] == "accepted"
    assert facts(session, original)["officer_effective_date"][0].validation_status == "verified"
    assert client.get("/review").json() == []
    again = client.post(f"/review/{queued[0]['id']}/resolve", json={"accept": False})
    assert again.status_code == 409


def test_rejected_review_keeps_the_fact_as_rejected(session, original, store, client) -> None:
    run(session, original, store, [EFFECTIVE | {"confidence": 0.4}])
    review = session.scalar(select(ReviewQueue))

    client.post(f"/review/{review.id}/resolve", json={"accept": False})

    stored = facts(session, original)["officer_effective_date"][0]
    assert stored.validation_status == "rejected"
    assert stored.span_start is not None


def test_api_exposes_current_facts_full_history_and_the_chain(
    session, original, amendment, store, client
) -> None:
    run(session, original, store, [EFFECTIVE, SALARY])
    run(session, amendment, store, [AMENDED])

    documents = client.get("/documents").json()
    current = client.get(f"/documents/{original.id}/facts").json()
    everything = client.get(f"/documents/{original.id}/facts", params={"current": False}).json()
    amended_id = client.get(f"/documents/{amendment.id}/facts").json()[0]["id"]
    history = client.get(f"/facts/{amended_id}/history").json()

    assert [d["doc_type"] for d in documents] == ["8-K/A", "8-K"]
    assert documents[0]["supersedes_id"] == str(original.id)
    assert [f["field_name"] for f in current] == ["transaction_amount"]
    assert len(everything) == 2
    assert [f["value_raw"] for f in history] == ["June 15, 2026", "May 1, 2026"]
    assert history[1]["document_id"] == str(original.id)
    missing = client.get("/facts/00000000-0000-0000-0000-000000000000/history")
    assert missing.status_code == 404
