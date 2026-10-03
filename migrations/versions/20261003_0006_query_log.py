"""query log

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-03 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "query_log",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieved_chunk_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("not_found", sa.Boolean(), nullable=False),
        sa.Column("claims_dropped", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_retrieval_ms", sa.Float(), nullable=True),
        sa.Column("latency_rerank_ms", sa.Float(), nullable=True),
        sa.Column("latency_ttft_ms", sa.Float(), nullable=True),
        sa.Column("latency_total_ms", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_log")),
    )
    op.create_index(op.f("ix_query_log_created_at"), "query_log", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_query_log_created_at"), table_name="query_log")
    op.drop_table("query_log")
