"""chunk table with vector and text indexes

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-02 14:39:29.357202

"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "chunk",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_strategy", sa.String(length=32), nullable=False),
        sa.Column("text_version", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=16), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=False),
        sa.Column("span_end", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "span_start >= 0 AND span_end > span_start", name=op.f("ck_chunk_span_ordered")
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["source_document.id"],
            name=op.f("fk_chunk_document_id_source_document"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_strategy",
            "text_version",
            "embedding_model",
            "ordinal",
            name=op.f("uq_chunk_document_id"),
        ),
    )
    op.create_index(op.f("ix_chunk_document_id"), "chunk", ["document_id"], unique=False)
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_chunk_strategy", "chunk", ["chunk_strategy", "embedding_model"], unique=False
    )
    op.create_index("ix_chunk_tsv", "chunk", ["tsv"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunk_tsv", table_name="chunk", postgresql_using="gin")
    op.drop_index("ix_chunk_strategy", table_name="chunk")
    op.drop_index(
        "ix_chunk_embedding_hnsw",
        table_name="chunk",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_chunk_document_id"), table_name="chunk")
    op.drop_table("chunk")
