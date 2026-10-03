from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.ingest import ingest_filings
from anchor.models import SourceDocument
from anchor.storage import RawStore, content_hash
from edgar_fakes import CIK, DOCUMENTS, EXHIBIT_PATH, FakeEdgar


def documents(session: Session) -> list[SourceDocument]:
    """Filings only, oldest first; exhibits are checked separately."""
    query = select(SourceDocument).where(SourceDocument.parent_id.is_(None))
    return list(session.scalars(query.order_by(SourceDocument.published_at)))


def exhibits(session: Session) -> list[SourceDocument]:
    return list(session.scalars(select(SourceDocument).where(SourceDocument.parent_id.isnot(None))))


def test_ingest_stores_raw_bytes_and_a_matching_row(session: Session, tmp_path: Path) -> None:
    store = RawStore(tmp_path)

    result = ingest_filings(session, FakeEdgar().client(min_interval=0), store, CIK)

    assert (result.seen, result.stored, result.skipped) == (2, 2, 0)
    original, amendment = documents(session)
    assert (original.doc_type, amendment.doc_type) == ("8-K", "8-K/A")
    assert original.external_id == "0000320193-26-000015"
    assert original.publisher == "Example Corp"
    assert original.publisher_id == str(CIK)
    raw = store.get(original.raw_path)
    assert raw == DOCUMENTS["/Archives/edgar/data/320193/000032019326000015/results.htm"]
    assert original.content_hash == content_hash(raw)


def test_second_run_adds_nothing_and_downloads_nothing(session: Session, tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    ingest_filings(session, FakeEdgar().client(min_interval=0), store, CIK)
    edgar = FakeEdgar()

    result = ingest_filings(session, edgar.client(min_interval=0), store, CIK)

    assert (result.seen, result.stored, result.skipped) == (2, 0, 2)
    assert edgar.downloads() == []
    assert len(documents(session)) == 2


def test_limit_takes_the_newest_filings(session: Session, tmp_path: Path) -> None:
    result = ingest_filings(
        session, FakeEdgar().client(min_interval=0), RawStore(tmp_path), CIK, limit=1
    )

    assert result.stored == 1
    assert [d.doc_type for d in documents(session)] == ["8-K/A"]


def test_identical_content_under_a_new_accession_is_not_stored_twice(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    same = b"<html>identical</html>"
    monkeypatch.setattr("edgar_fakes.DOCUMENTS", dict.fromkeys(DOCUMENTS, same))

    result = ingest_filings(session, FakeEdgar().client(min_interval=0), RawStore(tmp_path), CIK)

    assert (result.stored, result.skipped) == (1, 1)
    assert len(documents(session)) == 1


def test_exhibit_99_press_release_is_stored_and_linked_to_its_filing(
    session: Session, tmp_path: Path
) -> None:
    store = RawStore(tmp_path)

    result = ingest_filings(session, FakeEdgar().client(min_interval=0), store, CIK)

    assert result.exhibits == 1
    (exhibit,) = exhibits(session)
    parent = next(d for d in documents(session) if d.external_id == "0000320193-26-000015")
    assert exhibit.parent_id == parent.id
    assert exhibit.doc_type == "EX-99.1"
    assert exhibit.external_id == "0000320193-26-000015/a8-kex991q2.htm"
    assert store.get(exhibit.raw_path) == DOCUMENTS[EXHIBIT_PATH]


def test_exhibits_are_backfilled_for_filings_ingested_without_them(
    session: Session, tmp_path: Path
) -> None:
    store = RawStore(tmp_path)
    ingest_filings(session, FakeEdgar().client(min_interval=0), store, CIK, with_exhibits=False)
    edgar = FakeEdgar()

    result = ingest_filings(session, edgar.client(min_interval=0), store, CIK)

    assert (result.stored, result.exhibits) == (0, 1)
    assert edgar.downloads() == [EXHIBIT_PATH]


def test_exhibits_can_be_skipped(session: Session, tmp_path: Path) -> None:
    result = ingest_filings(
        session, FakeEdgar().client(min_interval=0), RawStore(tmp_path), CIK, with_exhibits=False
    )

    assert result.exhibits == 0
    assert exhibits(session) == []
