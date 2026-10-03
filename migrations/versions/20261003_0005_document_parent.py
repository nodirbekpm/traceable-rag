"""document parent for exhibits

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("source_document", sa.Column("parent_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_source_document_parent_id"), "source_document", ["parent_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_source_document_parent_id_source_document"),
        "source_document",
        "source_document",
        ["parent_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_source_document_parent_id_source_document"),
        "source_document",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_source_document_parent_id"), table_name="source_document")
    op.drop_column("source_document", "parent_id")
