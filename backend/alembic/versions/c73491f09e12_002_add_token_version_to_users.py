"""002_add_token_version_to_users

Revision ID: c73491f09e12
Revises: be538555bf09
Create Date: 2026-09-25 16:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c73491f09e12"
down_revision: str | Sequence[str] | None = "be538555bf09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "token_version")
