"""add support contact settings

Revision ID: 20260907_0007
Revises: 20260905_0006
Create Date: 2026-09-07 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260907_0007"
down_revision: str | Sequence[str] | None = "20260905_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=40), nullable=True),
        sa.Column("whatsapp_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_support_settings_singleton"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_settings")),
    )


def downgrade() -> None:
    op.drop_table("support_settings")
