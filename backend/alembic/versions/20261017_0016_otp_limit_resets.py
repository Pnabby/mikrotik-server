"""Record administrator resets of OTP request allowances.

Revision ID: 20261017_0016
Revises: 20261008_0015
"""

import sqlalchemy as sa
from alembic import op

revision = "20261017_0016"
down_revision = "20261008_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "otp_limit_resets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("flow", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(384), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("admin_email", sa.String(320), nullable=False),
        sa.Column(
            "reset_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_otp_limit_resets_scope", "otp_limit_resets", ["flow", "subject", "reset_at"]
    )


def downgrade():
    op.drop_table("otp_limit_resets")
