"""Persist encrypted hostel transfer recovery operations.

Revision ID: 20261008_0015
Revises: 20261008_0014
"""

import sqlalchemy as sa

from alembic import op

revision = "20261008_0015"
down_revision = "20261008_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hostel_transfer_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("source_router_id", sa.String(64), nullable=False),
        sa.Column("destination_router_id", sa.String(64), nullable=False),
        sa.Column("destination_router_name", sa.String(120), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("encrypted_snapshot", sa.Text(), nullable=True),
        sa.Column("remaining_byte_limits", sa.JSON(), nullable=True),
        sa.Column("remaining_uptime_seconds", sa.Integer(), nullable=True),
        sa.Column("subscription_ids", sa.JSON(), nullable=False),
        sa.Column("source_user_id", sa.String(32), nullable=False),
        sa.Column("destination_user_id", sa.String(32), nullable=True),
        sa.Column("last_confirmed_state", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "source_router_id <> destination_router_id", name="transfer_distinct_routers"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="transfer_attempts_non_negative"),
        sa.CheckConstraint(
            "status IN ('running', 'reconciliation_required', 'manual_review', 'completed', 'rolled_back')",
            name="transfer_status",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_router_id"], ["routers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["destination_router_id"], ["routers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("customer_id", "status", "is_active", "next_retry_at"):
        op.create_index(
            f"ix_hostel_transfer_operations_{column}", "hostel_transfer_operations", [column]
        )
    op.create_index(
        "uq_hostel_transfer_active_customer",
        "hostel_transfer_operations",
        ["customer_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade():
    # An operator must reconcile unfinished operations before downgrading.
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM hostel_transfer_operations WHERE is_active")
    ):
        raise RuntimeError("Unfinished hostel transfers must be resolved before downgrading.")
    op.drop_table("hostel_transfer_operations")
