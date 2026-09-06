"""record customer legal acceptance and account activity

Revision ID: 20260905_0006
Revises: 20260905_0005
Create Date: 2026-09-05 17:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0006"
down_revision: str | Sequence[str] | None = "20260905_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("last_activity_at", sa.DateTime(timezone=True)))
    op.add_column("customers", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("customers", sa.Column("terms_version", sa.String(length=20)))
    op.add_column("customers", sa.Column("privacy_notice_version", sa.String(length=20)))
    op.execute(
        """
        UPDATE customers
        SET last_activity_at = COALESCE(last_login_at, created_at),
            terms_accepted_at = created_at,
            terms_version = 'legacy-2026-09-05',
            privacy_notice_version = 'legacy-2026-09-05'
        """
    )
    op.alter_column("customers", "last_activity_at", nullable=False)
    op.alter_column("customers", "terms_accepted_at", nullable=False)
    op.alter_column("customers", "terms_version", nullable=False)
    op.alter_column("customers", "privacy_notice_version", nullable=False)
    op.create_index(
        op.f("ix_customers_last_activity_at"),
        "customers",
        ["last_activity_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_customers_last_activity_at"), table_name="customers")
    op.drop_column("customers", "privacy_notice_version")
    op.drop_column("customers", "terms_version")
    op.drop_column("customers", "terms_accepted_at")
    op.drop_column("customers", "last_activity_at")
