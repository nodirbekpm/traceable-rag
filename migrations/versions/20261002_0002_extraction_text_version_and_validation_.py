"""extraction text version and validation reason

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02 12:30:21.970785

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("extracted_fact", sa.Column("validation_reason", sa.Text(), nullable=True))
    op.add_column(
        "extraction_run", sa.Column("text_version", sa.Text(), server_default="t1", nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("extraction_run", "text_version")
    op.drop_column("extracted_fact", "validation_reason")
