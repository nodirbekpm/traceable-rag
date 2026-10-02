"""Chunk and embed ingested filings: `python -m anchor.index`."""

import argparse
import logging
import time

from sqlalchemy import select

from anchor.chunking import STRATEGIES
from anchor.config import get_settings
from anchor.db import get_sessionmaker
from anchor.embedding import build_embedder
from anchor.indexing import index_document
from anchor.models import SourceDocument
from anchor.storage import RawStore

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=[*STRATEGIES, "all"], default="all")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    strategies = tuple(STRATEGIES) if args.strategy == "all" else (args.strategy,)
    store = RawStore(settings.raw_storage_dir)
    embedder = build_embedder(settings)
    chunks = 0
    started = time.perf_counter()
    with get_sessionmaker()() as session:
        for document in session.scalars(select(SourceDocument)).all():
            chunks += index_document(session, document, store, embedder, strategies).chunks
    elapsed = time.perf_counter() - started
    rate = chunks / elapsed if elapsed and chunks else 0.0
    logger.info(
        "model=%s chunks=%d seconds=%.1f chunks_per_second=%.0f",
        embedder.model_name,
        chunks,
        elapsed,
        rate,
    )


if __name__ == "__main__":
    main()
