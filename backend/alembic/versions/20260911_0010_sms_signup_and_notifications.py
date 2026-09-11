"""bind signup OTPs to phone and track activation notifications

Revision ID: 20260911_0010
Revises: 20260911_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0010"
down_revision: str | Sequence[str] | None = "20260911_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.alter_column(
            "email_verified_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )
    with op.batch_alter_table("email_otp_challenges") as batch_op:
        batch_op.add_column(sa.Column("phone_number", sa.String(length=16), nullable=True))
        batch_op.create_index("ix_email_otp_challenges_phone_number", ["phone_number"])
    with op.batch_alter_table("activations") as batch_op:
        batch_op.add_column(sa.Column("sms_notified_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("email_notified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    # Accounts created with SMS-only verification have no email verification timestamp.
    # A downgrade cannot safely make this column non-null without inventing verification.
    op.execute(
        "UPDATE customers SET email_verified_at = created_at WHERE email_verified_at IS NULL"
    )
    with op.batch_alter_table("customers") as batch_op:
        batch_op.alter_column(
            "email_verified_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
    with op.batch_alter_table("activations") as batch_op:
        batch_op.drop_column("email_notified_at")
        batch_op.drop_column("sms_notified_at")
    with op.batch_alter_table("email_otp_challenges") as batch_op:
        batch_op.drop_index("ix_email_otp_challenges_phone_number")
        batch_op.drop_column("phone_number")
