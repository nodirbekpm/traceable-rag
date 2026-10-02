"""Chunk documents, embed the chunks and store them for retrieval."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.chunking import STRATEGIES
from anchor.embedding import Embedder
from anchor.models import EMBEDDING_DIMENSIONS, Chunk, SourceDocument
from anchor.storage import RawStore
from anchor.text import TEXT_VERSION, html_to_text

logger = logging.getLogger(__name__)


@dataclass
class IndexResult:
    chunks: int = 0
    skipped_strategies: int = 0


def index_document(
    session: Session,
    document: SourceDocument,
    store: RawStore,
    embedder: Embedder,
    strategies: tuple[str, ...] = tuple(STRATEGIES),
) -> IndexResult:
    """Index one document under each strategy. Already indexed combinations are skipped."""
    if embedder.dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{embedder.model_name} produces {embedder.dimensions}-dimensional vectors, "
            f"but the chunk table stores {EMBEDDING_DIMENSIONS}; a migration is required."
        )
    result = IndexResult()
    text: str | None = None
    for strategy in strategies:
        exists = session.scalar(
            select(Chunk.id)
            .where(
                Chunk.document_id == document.id,
                Chunk.chunk_strategy == strategy,
                Chunk.text_version == TEXT_VERSION,
                Chunk.embedding_model == embedder.model_name,
            )
            .limit(1)
        )
        if exists is not None:
            result.skipped_strategies += 1
            continue
        if text is None:
            text = html_to_text(store.get(document.raw_path))
        chunks = STRATEGIES[strategy](text)
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        session.add_all(
            Chunk(
                document_id=document.id,
                chunk_strategy=strategy,
                text_version=TEXT_VERSION,
                embedding_model=embedder.model_name,
                ordinal=chunk.ordinal,
                section=chunk.section,
                text=chunk.text,
                span_start=chunk.span_start,
                span_end=chunk.span_end,
                embedding=vector,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        result.chunks += len(chunks)
    session.commit()
    return result
