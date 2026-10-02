"""extraction run version key

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02 13:04:50.761116

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "uq_extraction_run_version_key",
        "extraction_run",
        ["document_id", "model_name", "prompt_version", "schema_version", "text_version"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_extraction_run_version_key",
        table_name="extraction_run",
        postgresql_where=sa.text("status = 'succeeded'"),
    )
