import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anchor.models import ExtractedFact, ExtractionRun, SourceDocument


def make_document(session: Session, content_hash: str = "a" * 64, **overrides) -> SourceDocument:
    fields = {
        "source_url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/doc.htm",
        "doc_type": "8-K",
        "publisher": "Example Corp",
        "content_hash": content_hash,
        "raw_path": f"{content_hash[:2]}/{content_hash}",
    }
    document = SourceDocument(**(fields | overrides))
    session.add(document)
    session.flush()
    return document


def make_run(session: Session, document: SourceDocument) -> ExtractionRun:
    run = ExtractionRun(
        document_id=document.id,
        model_name="test-model",
        model_version="1",
        prompt_version="p1",
        schema_version="s1",
    )
    session.add(run)
    session.flush()
    return run


def test_duplicate_content_hash_is_rejected(session: Session) -> None:
    make_document(session)

    with pytest.raises(IntegrityError):
        make_document(session)


def test_amendment_links_to_the_document_it_supersedes(session: Session) -> None:
    original = make_document(session, "a" * 64)
    amendment = make_document(session, "b" * 64, doc_type="8-K/A", supersedes_id=original.id)

    found = session.scalar(
        select(SourceDocument).where(SourceDocument.supersedes_id == original.id)
    )

    assert found is not None
    assert found.id == amendment.id


def test_fact_defaults_to_current_and_pending(session: Session) -> None:
    document = make_document(session)
    run = make_run(session, document)
    fact = ExtractedFact(run_id=run.id, document_id=document.id, field_name="revenue")
    session.add(fact)
    session.flush()
    session.refresh(fact)

    assert fact.is_current is True
    assert fact.validation_status == "pending"


def test_verified_fact_without_source_span_is_rejected(session: Session) -> None:
    document = make_document(session)
    run = make_run(session, document)
    session.add(
        ExtractedFact(
            run_id=run.id,
            document_id=document.id,
            field_name="revenue",
            value_raw="$4.2M",
            validation_status="verified",
        )
    )

    with pytest.raises(IntegrityError, match="verified_requires_span"):
        session.flush()


def test_verified_fact_with_source_span_is_accepted(session: Session) -> None:
    document = make_document(session)
    run = make_run(session, document)
    fact = ExtractedFact(
        run_id=run.id,
        document_id=document.id,
        field_name="revenue",
        value_raw="$4.2M",
        span_start=120,
        span_end=125,
        source_excerpt="revenue of $4.2M for the quarter",
        validation_status="verified",
    )
    session.add(fact)
    session.flush()

    assert fact.id is not None


def test_inverted_span_is_rejected(session: Session) -> None:
    document = make_document(session)
    run = make_run(session, document)
    session.add(
        ExtractedFact(
            run_id=run.id,
            document_id=document.id,
            field_name="revenue",
            span_start=50,
            span_end=10,
        )
    )

    with pytest.raises(IntegrityError, match="span_ordered"):
        session.flush()
