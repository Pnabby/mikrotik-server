"""allow plans without duration and add displayed download speed

Revision ID: 20260903_0004
Revises: 20260903_0003
Create Date: 2026-09-03 19:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0004"
down_revision: str | Sequence[str] | None = "20260903_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_packages_package_duration_positive"),
        "packages",
        type_="check",
    )
    op.alter_column(
        "packages",
        "duration_seconds",
        existing_type=sa.BigInteger(),
        nullable=True,
    )
    op.create_check_constraint(
        op.f("ck_packages_package_duration_positive"),
        "packages",
        "duration_seconds IS NULL OR duration_seconds > 0",
    )
    op.add_column(
        "router_package_profiles",
        sa.Column("download_speed", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("router_package_profiles", "download_speed")
    op.execute("UPDATE packages SET duration_seconds = 86400 WHERE duration_seconds IS NULL")
    op.drop_constraint(
        op.f("ck_packages_package_duration_positive"),
        "packages",
        type_="check",
    )
    op.alter_column(
        "packages",
        "duration_seconds",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_check_constraint(
        op.f("ck_packages_package_duration_positive"),
        "packages",
        "duration_seconds > 0",
    )
