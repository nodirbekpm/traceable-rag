"""core tables

Revision ID: 0001
Revises:
Create Date: 2026-10-02 11:45:37.387187

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enabled up front so later migrations can add embedding columns without superuser steps.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "source_document",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=True),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("publisher_id", sa.String(length=32), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_path", sa.Text(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["source_document.id"],
            name=op.f("fk_source_document_supersedes_id_source_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_document")),
        sa.UniqueConstraint("content_hash", name=op.f("uq_source_document_content_hash")),
        sa.UniqueConstraint("external_id", name=op.f("uq_source_document_external_id")),
    )
    op.create_index(
        op.f("ix_source_document_doc_type"), "source_document", ["doc_type"], unique=False
    )
    op.create_index(
        op.f("ix_source_document_publisher_id"), "source_document", ["publisher_id"], unique=False
    )
    op.create_index(
        op.f("ix_source_document_supersedes_id"), "source_document", ["supersedes_id"], unique=False
    )
    op.create_table(
        "extraction_run",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("chunk_strategy", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name=op.f("ck_extraction_run_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_document.id"],
            name=op.f("fk_extraction_run_document_id_source_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extraction_run")),
    )
    op.create_index(
        op.f("ix_extraction_run_document_id"), "extraction_run", ["document_id"], unique=False
    )
    op.create_table(
        "extracted_fact",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("value_raw", sa.Text(), nullable=True),
        sa.Column("value_normalized", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("source_excerpt", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "validation_status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "validation_status <> 'verified' OR (span_start IS NOT NULL AND span_end IS NOT NULL AND source_excerpt IS NOT NULL)",
            name=op.f("ck_extracted_fact_verified_requires_span"),
        ),
        sa.CheckConstraint(
            "validation_status IN ('pending', 'verified', 'hallucinated', 'rejected', 'needs_review')",
            name=op.f("ck_extracted_fact_validation_valid"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_extracted_fact_confidence_range"),
        ),
        sa.CheckConstraint(
            "span_start IS NULL OR (span_start >= 0 AND span_end > span_start)",
            name=op.f("ck_extracted_fact_span_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_document.id"],
            name=op.f("fk_extracted_fact_document_id_source_document"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["extraction_run.id"], name=op.f("fk_extracted_fact_run_id_extraction_run")
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["extracted_fact.id"],
            name=op.f("fk_extracted_fact_superseded_by_extracted_fact"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_fact")),
    )
    op.create_index(
        "ix_extracted_fact_current",
        "extracted_fact",
        ["document_id", "field_name"],
        unique=False,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(op.f("ix_extracted_fact_run_id"), "extracted_fact", ["run_id"], unique=False)
    op.create_table(
        "review_queue",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fact_id"], ["extracted_fact.id"], name=op.f("fk_review_queue_fact_id_extracted_fact")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_queue")),
    )
    op.create_index(op.f("ix_review_queue_fact_id"), "review_queue", ["fact_id"], unique=False)
    op.create_index(
        "ix_review_queue_open",
        "review_queue",
        ["created_at"],
        unique=False,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_review_queue_open",
        table_name="review_queue",
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.drop_index(op.f("ix_review_queue_fact_id"), table_name="review_queue")
    op.drop_table("review_queue")
    op.drop_index(op.f("ix_extracted_fact_run_id"), table_name="extracted_fact")
    op.drop_index(
        "ix_extracted_fact_current",
        table_name="extracted_fact",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("extracted_fact")
    op.drop_index(op.f("ix_extraction_run_document_id"), table_name="extraction_run")
    op.drop_table("extraction_run")
    op.drop_index(op.f("ix_source_document_supersedes_id"), table_name="source_document")
    op.drop_index(op.f("ix_source_document_publisher_id"), table_name="source_document")
    op.drop_index(op.f("ix_source_document_doc_type"), table_name="source_document")
    op.drop_table("source_document")
