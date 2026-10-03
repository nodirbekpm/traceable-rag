"""Fetch 8-K / 8-K/A filings from EDGAR into raw storage and `source_document`."""

import argparse
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.config import get_settings
from anchor.db import get_sessionmaker
from anchor.edgar import EdgarClient, Filing
from anchor.models import SourceDocument
from anchor.storage import RawStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    seen: int = 0
    stored: int = 0
    skipped: int = 0
    exhibits: int = 0


def _store(session: Session, store: RawStore, content: bytes, **fields) -> SourceDocument | None:
    """Save the bytes and a `source_document` row; None if identical content is already known."""
    blob = store.put(content)
    same_content = session.scalar(
        select(SourceDocument.id).where(SourceDocument.content_hash == blob.content_hash)
    )
    if same_content is not None:
        logger.warning("%s duplicates document %s; skipped", fields["external_id"], same_content)
        return None
    document = SourceDocument(content_hash=blob.content_hash, raw_path=blob.relative_path, **fields)
    session.add(document)
    # Commit per document so an interrupted run keeps what it already fetched.
    session.commit()
    return document


def _ingest_exhibits(
    session: Session, client: EdgarClient, store: RawStore, filing: Filing, parent: SourceDocument
) -> int:
    stored = 0
    for exhibit in client.list_exhibits(filing):
        known = session.scalar(
            select(SourceDocument.id).where(SourceDocument.external_id == exhibit.external_id)
        )
        if known is not None:
            continue
        document = _store(
            session,
            store,
            client.download_url(exhibit.url),
            source_url=exhibit.url,
            external_id=exhibit.external_id,
            doc_type=exhibit.doc_type,
            publisher=filing.company,
            publisher_id=str(filing.cik),
            published_at=filing.filed_at,
            parent_id=parent.id,
        )
        stored += document is not None
    return stored


def ingest_filings(
    session: Session,
    client: EdgarClient,
    store: RawStore,
    cik: int,
    *,
    limit: int | None = None,
    forms: tuple[str, ...] = ("8-K", "8-K/A"),
    with_exhibits: bool = True,
    accessions: set[str] | None = None,
) -> IngestResult:
    """Ingest a company's filings and their Exhibit 99 press releases.

    Safe to re-run: known documents are never downloaded again. The exhibit list
    of a known filing is re-read (one small request) so older ingests get backfilled.
    """
    result = IngestResult()
    for filing in client.list_filings(cik, forms):
        if limit is not None and result.seen >= limit:
            break
        # A fixed list of filings makes a corpus reproducible, unlike "the newest N".
        if accessions is not None and filing.accession_number not in accessions:
            continue
        result.seen += 1

        document = session.scalar(
            select(SourceDocument).where(SourceDocument.external_id == filing.accession_number)
        )
        if document is not None:
            result.skipped += 1
        else:
            document = _store(
                session,
                store,
                client.download(filing),
                source_url=filing.url,
                external_id=filing.accession_number,
                doc_type=filing.form,
                publisher=filing.company,
                publisher_id=str(filing.cik),
                published_at=filing.filed_at,
            )
            if document is None:
                result.skipped += 1
                continue
            result.stored += 1
        if with_exhibits:
            result.exhibits += _ingest_exhibits(session, client, store, filing, document)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cik", type=int, required=True, help="company CIK, e.g. 320193")
    parser.add_argument("--limit", type=int, default=None, help="newest N filings only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    store = RawStore(settings.raw_storage_dir)
    with EdgarClient(settings.edgar_user_agent) as client, get_sessionmaker()() as session:
        result = ingest_filings(session, client, store, args.cik, limit=args.limit)
    logger.info(
        "cik=%s seen=%d stored=%d skipped=%d exhibits=%d",
        args.cik,
        result.seen,
        result.stored,
        result.skipped,
        result.exhibits,
    )


if __name__ == "__main__":
    main()
