"""eval result

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "eval_result",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("suite", sa.String(length=16), nullable=False),
        sa.Column("run_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("avg_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("p50_ms", sa.Float(), nullable=True),
        sa.Column("p95_ms", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "suite IN ('extraction', 'retrieval', 'answer')",
            name=op.f("ck_eval_result_suite_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_result")),
    )
    op.create_index(op.f("ix_eval_result_suite"), "eval_result", ["suite"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_eval_result_suite"), table_name="eval_result")
    op.drop_table("eval_result")
