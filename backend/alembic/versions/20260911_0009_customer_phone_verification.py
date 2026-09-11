"""add customer phone verification

Revision ID: 20260911_0009
Revises: 20260907_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0009"
down_revision: str | Sequence[str] | None = "20260907_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("phone_number", sa.String(length=16), nullable=True))
        batch_op.add_column(
            sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_customers_phone_number", ["phone_number"], unique=True)
    op.create_table(
        "phone_otp_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("phone_number", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_phone_otp_challenges_customer_id", "phone_otp_challenges", ["customer_id"])
    op.create_index(
        "ix_phone_otp_challenges_phone_number", "phone_otp_challenges", ["phone_number"]
    )
    op.create_index("ix_phone_otp_challenges_expires_at", "phone_otp_challenges", ["expires_at"])
    op.create_index("ix_phone_otp_challenges_created_at", "phone_otp_challenges", ["created_at"])


def downgrade() -> None:
    op.drop_table("phone_otp_challenges")
    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_index("ix_customers_phone_number")
        batch_op.drop_column("phone_verified_at")
        batch_op.drop_column("phone_number")
