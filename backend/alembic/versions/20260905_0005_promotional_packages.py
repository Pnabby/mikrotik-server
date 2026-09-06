"""add promotional packages

Revision ID: 20260905_0005
Revises: 20260903_0004
Create Date: 2026-09-05 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0005"
down_revision: str | Sequence[str] | None = "20260903_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "packages",
        sa.Column(
            "is_promotional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("packages", "is_promotional")
