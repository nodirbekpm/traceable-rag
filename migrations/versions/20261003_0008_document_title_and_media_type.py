"""document title and media type

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-03 16:26:46.067307

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("source_document", sa.Column("title", sa.Text(), nullable=True))
    op.add_column(
        "source_document",
        sa.Column("media_type", sa.String(length=128), server_default="text/html", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("source_document", "media_type")
    op.drop_column("source_document", "title")
