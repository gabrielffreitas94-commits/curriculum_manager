"""003_add_gemini_model_and_thinking_to_user_settings

Revision ID: a1b2c3d4e5f6
Revises: c73491f09e12
Create Date: 2026-09-26 01:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "c73491f09e12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user_settings",
        sa.Column(
            "gemini_model",
            sa.String(length=50),
            server_default="gemini-2.5-flash",
            nullable=False,
        ),
    )
    op.add_column(
        "user_settings",
        sa.Column(
            "gemini_thinking_level",
            sa.String(length=20),
            server_default="medium",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user_settings", "gemini_thinking_level")
    op.drop_column("user_settings", "gemini_model")
