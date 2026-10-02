"""Extract facts from ingested filings: `python -m anchor.extract --limit 5`."""

import argparse
import logging

from sqlalchemy import func, select

from anchor.config import get_settings
from anchor.db import get_sessionmaker
from anchor.extraction.extractor import extract_document
from anchor.llm import build_llm
from anchor.models import ExtractedFact, SourceDocument
from anchor.storage import RawStore

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="newest N documents only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    llm = build_llm(settings)
    store = RawStore(settings.raw_storage_dir)
    with get_sessionmaker()() as session:
        documents = session.scalars(
            select(SourceDocument).order_by(SourceDocument.published_at.desc()).limit(args.limit)
        ).all()
        for document in documents:
            run = extract_document(session, document, llm, store, settings)
            counts = dict(
                session.execute(
                    select(ExtractedFact.validation_status, func.count())
                    .where(ExtractedFact.run_id == run.id)
                    .group_by(ExtractedFact.validation_status)
                ).all()
            )
            logger.info(
                "%s %s run=%s tokens=%s/%s cost=$%s facts=%s",
                document.doc_type,
                document.external_id,
                run.status,
                run.token_input,
                run.token_output,
                run.cost_usd,
                counts,
            )


if __name__ == "__main__":
    main()
