"""Fetch 8-K / 8-K/A filings from EDGAR into raw storage and `source_document`."""

import argparse
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.config import get_settings
from anchor.db import get_sessionmaker
from anchor.edgar import EdgarClient
from anchor.models import SourceDocument
from anchor.storage import RawStore

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    seen: int = 0
    stored: int = 0
    skipped: int = 0


def ingest_filings(
    session: Session,
    client: EdgarClient,
    store: RawStore,
    cik: int,
    *,
    limit: int | None = None,
    forms: tuple[str, ...] = ("8-K", "8-K/A"),
) -> IngestResult:
    """Ingest a company's filings. Safe to re-run: known filings are not downloaded again."""
    result = IngestResult()
    for filing in client.list_filings(cik, forms):
        if limit is not None and result.seen >= limit:
            break
        result.seen += 1

        known = session.scalar(
            select(SourceDocument.id).where(SourceDocument.external_id == filing.accession_number)
        )
        if known is not None:
            result.skipped += 1
            continue

        blob = store.put(client.download(filing))
        same_content = session.scalar(
            select(SourceDocument.id).where(SourceDocument.content_hash == blob.content_hash)
        )
        if same_content is not None:
            logger.warning(
                "%s has the same content as document %s; skipped",
                filing.accession_number,
                same_content,
            )
            result.skipped += 1
            continue

        session.add(
            SourceDocument(
                source_url=filing.url,
                external_id=filing.accession_number,
                doc_type=filing.form,
                publisher=filing.company,
                publisher_id=str(filing.cik),
                published_at=filing.filed_at,
                content_hash=blob.content_hash,
                raw_path=blob.relative_path,
            )
        )
        # Commit per document so an interrupted run keeps what it already fetched.
        session.commit()
        result.stored += 1
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
        "cik=%s seen=%d stored=%d skipped=%d", args.cik, result.seen, result.stored, result.skipped
    )


if __name__ == "__main__":
    main()
