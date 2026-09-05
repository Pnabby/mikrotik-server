"""add hostel-specific profile presentation

Revision ID: 20260903_0003
Revises: 20260903_0002
Create Date: 2026-09-03 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0003"
down_revision: str | Sequence[str] | None = "20260903_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "router_package_profiles",
        sa.Column("display_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "router_package_profiles",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("router_package_profiles", "description")
    op.drop_column("router_package_profiles", "display_name")
