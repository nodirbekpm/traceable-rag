"""Vector, keyword and hybrid search over chunks.

All three modes share one signature so the eval harness can compare them on
the same questions. Hybrid fuses the two ranked lists with Reciprocal Rank
Fusion, which needs no score calibration between cosine distance and ts_rank.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from sqlalchemy import Text, cast, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.orm import Session

from anchor.config import get_settings
from anchor.embedding import Embedder
from anchor.models import Chunk, SourceDocument

Mode = Literal["vector", "text", "hybrid"]
MODES: tuple[Mode, ...] = ("vector", "text", "hybrid")
RRF_K = 60


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    text: str
    span_start: int
    span_end: int
    section: str | None
    doc_type: str
    external_id: str | None
    publisher: str
    published_at: datetime | None
    score: float
    # True when a later amendment replaces this document.
    superseded: bool = False


def _hits(session: Session, rows: Sequence, scores: Sequence[float]) -> list[Hit]:
    document_ids = {chunk.document_id for chunk, _ in rows}
    superseded = set(
        session.scalars(
            select(SourceDocument.supersedes_id).where(
                SourceDocument.supersedes_id.in_(document_ids)
            )
        )
    )
    return [
        Hit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            text=chunk.text,
            span_start=chunk.span_start,
            span_end=chunk.span_end,
            section=chunk.section,
            doc_type=document.doc_type,
            external_id=document.external_id,
            publisher=document.publisher,
            published_at=document.published_at,
            score=float(score),
            superseded=chunk.document_id in superseded,
        )
        for (chunk, document), score in zip(rows, scores, strict=True)
    ]


def _scope(strategy: str, embedding_model: str):
    return (
        select(Chunk, SourceDocument)
        .join(SourceDocument, SourceDocument.id == Chunk.document_id)
        .where(Chunk.chunk_strategy == strategy, Chunk.embedding_model == embedding_model)
    )


def search_vector(
    session: Session, query_vector: list[float], *, strategy: str, embedding_model: str, k: int
) -> list[Hit]:
    # Recall/latency knob of the HNSW index; scoped to the current transaction.
    session.execute(
        select(func.set_config("hnsw.ef_search", str(get_settings().hnsw_ef_search), True))
    )
    distance = Chunk.embedding.cosine_distance(query_vector)
    rows = session.execute(
        _scope(strategy, embedding_model).add_columns(distance).order_by(distance).limit(k)
    ).all()
    return _hits(session, [(c, d) for c, d, _ in rows], [1 - dist for _, _, dist in rows])


def keyword_query(question: str):
    """Any-word match: plainto_tsquery joins lexemes with AND, which is too strict for questions."""
    plain = cast(func.plainto_tsquery("english", question), Text)
    return cast(func.replace(plain, "&", "|"), TSQUERY)


def search_text(
    session: Session, question: str, *, strategy: str, embedding_model: str, k: int
) -> list[Hit]:
    query = keyword_query(question)
    rank = func.ts_rank_cd(Chunk.tsv, query)
    rows = session.execute(
        _scope(strategy, embedding_model)
        .add_columns(rank)
        .where(Chunk.tsv.op("@@")(query))
        .order_by(rank.desc(), Chunk.ordinal)
        .limit(k)
    ).all()
    return _hits(session, [(c, d) for c, d, _ in rows], [score for _, _, score in rows])


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Hit]], k: int) -> list[Hit]:
    fused: dict[uuid.UUID, float] = {}
    first_seen: dict[uuid.UUID, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            first_seen.setdefault(hit.chunk_id, hit)
    ordered = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)[:k]
    return [replace(first_seen[chunk_id], score=fused[chunk_id]) for chunk_id in ordered]


def retrieve(
    session: Session,
    embedder: Embedder,
    question: str,
    *,
    mode: Mode = "hybrid",
    strategy: str = "section",
    k: int = 20,
) -> list[Hit]:
    scope = {"strategy": strategy, "embedding_model": embedder.model_name}
    if mode == "text":
        return search_text(session, question, k=k, **scope)
    query_vector = embedder.embed_query(question)
    if mode == "vector":
        return search_vector(session, query_vector, k=k, **scope)
    # Each list contributes deeper candidates than the final cut, so fusion has room to reorder.
    depth = max(k, 50)
    vector = search_vector(session, query_vector, k=depth, **scope)
    text = search_text(session, question, k=depth, **scope)
    return reciprocal_rank_fusion([vector, text], k)
