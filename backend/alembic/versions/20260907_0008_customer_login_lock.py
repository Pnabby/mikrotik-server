"""add persistent customer login lock

Revision ID: 20260907_0008
Revises: 20260907_0007
Create Date: 2026-09-07 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260907_0008"
down_revision: str | Sequence[str] | None = "20260907_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(
            sa.Column(
                "failed_login_attempts",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_customers_customer_failed_login_attempts_non_negative"),
            "failed_login_attempts >= 0",
        )
        batch_op.create_index("ix_customers_locked_at", ["locked_at"], unique=False)

    with op.batch_alter_table("email_otp_challenges") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_email_otp_challenges_otp_purpose"), type_="check"
        )
        batch_op.create_check_constraint(
            op.f("ck_email_otp_challenges_otp_purpose"),
            "purpose IN ('registration', 'username_recovery', 'pin_reset', 'account_unlock')",
        )


def downgrade() -> None:
    with op.batch_alter_table("email_otp_challenges") as batch_op:
        batch_op.drop_constraint(
            op.f("ck_email_otp_challenges_otp_purpose"), type_="check"
        )
        batch_op.create_check_constraint(
            op.f("ck_email_otp_challenges_otp_purpose"),
            "purpose IN ('registration', 'username_recovery', 'pin_reset')",
        )

    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_index("ix_customers_locked_at")
        batch_op.drop_constraint(
            op.f("ck_customers_customer_failed_login_attempts_non_negative"),
            type_="check",
        )
        batch_op.drop_column("locked_at")
        batch_op.drop_column("failed_login_attempts")
