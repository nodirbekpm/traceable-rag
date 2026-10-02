"""Anchor Core tables.

Two of the project's guarantees are enforced here rather than in application code:
a fact cannot be `verified` without a source span, and nothing is ever deleted --
superseded rows stay in place with `is_current = false`.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

RUN_STATUSES = ("pending", "running", "succeeded", "failed")
# Dimension of the default local embedding model (BAAI/bge-small-en-v1.5).
EMBEDDING_DIMENSIONS = 384

VALIDATION_STATUSES = ("pending", "verified", "hallucinated", "rejected", "needs_review")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    # Explicit names keep migrations deterministic and constraints droppable.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))


class SourceDocument(Base):
    __tablename__ = "source_document"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_url: Mapped[str] = mapped_column(Text)
    # Publisher-assigned identifier; for EDGAR this is the accession number.
    external_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    doc_type: Mapped[str] = mapped_column(String(16), index=True)
    publisher: Mapped[str] = mapped_column(Text)
    publisher_id: Mapped[str | None] = mapped_column(String(32), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # SHA-256 of the raw bytes exactly as received.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    raw_path: Mapped[str] = mapped_column(Text)
    # An amendment (8-K/A) points at the filing it replaces.
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_document.id"), index=True
    )


class ExtractionRun(Base):
    __tablename__ = "extraction_run"
    __table_args__ = (
        CheckConstraint(_in("status", RUN_STATUSES), name="status_valid"),
        # Idempotency key: the same document is never extracted twice with the same
        # model, prompt, schema and text version. Failed runs may be retried.
        Index(
            "uq_extraction_run_version_key",
            "document_id",
            "model_name",
            "prompt_version",
            "schema_version",
            "text_version",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_document.id"), index=True)
    model_name: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    # Version of the HTML->text conversion that span offsets in this run refer to.
    text_version: Mapped[str] = mapped_column(Text, server_default="t1")
    chunk_strategy: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    token_input: Mapped[int | None]
    token_output: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))


class ExtractedFact(Base):
    __tablename__ = "extracted_fact"
    __table_args__ = (
        CheckConstraint(_in("validation_status", VALIDATION_STATUSES), name="validation_valid"),
        CheckConstraint(
            "span_start IS NULL OR (span_start >= 0 AND span_end > span_start)",
            name="span_ordered",
        ),
        CheckConstraint(
            "validation_status <> 'verified' OR "
            "(span_start IS NOT NULL AND span_end IS NOT NULL AND source_excerpt IS NOT NULL)",
            name="verified_requires_span",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        # Reads almost always want the current value; history rows stay out of this index.
        Index(
            "ix_extracted_fact_current",
            "document_id",
            "field_name",
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extraction_run.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_document.id"))
    entity_id: Mapped[str | None] = mapped_column(Text)
    field_name: Mapped[str] = mapped_column(Text)
    value_raw: Mapped[str | None] = mapped_column(Text)
    value_normalized: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    span_start: Mapped[int | None]
    span_end: Mapped[int | None]
    source_excerpt: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    validation_status: Mapped[str] = mapped_column(String(16), server_default="pending")
    # Why a fact is not verified, e.g. "quote not found in source".
    validation_reason: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(server_default=text("true"))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extracted_fact.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewQueue(Base):
    __tablename__ = "review_queue"
    __table_args__ = (
        Index(
            "ix_review_queue_open",
            "created_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_fact.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        # One set of chunks per document, strategy, text conversion and embedding model.
        UniqueConstraint(
            "document_id", "chunk_strategy", "text_version", "embedding_model", "ordinal"
        ),
        CheckConstraint("span_start >= 0 AND span_end > span_start", name="span_ordered"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunk_strategy", "chunk_strategy", "embedding_model"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_document.id"), index=True)
    chunk_strategy: Mapped[str] = mapped_column(String(32))
    text_version: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(Text)
    ordinal: Mapped[int]
    # "2.02" for an Item section; set only by the section-aware strategy.
    section: Mapped[str | None] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    span_start: Mapped[int]
    span_end: Mapped[int]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )
