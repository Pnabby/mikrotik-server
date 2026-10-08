"""Add customer complaints and administrator replies.

Revision ID: 20261008_0014
Revises: 20260926_0013
"""

import sqlalchemy as sa
from alembic import op

revision = "20261008_0014"
down_revision = "20260926_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_issues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("router_id", sa.String(64), nullable=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("hostel_name", sa.String(120), nullable=False),
        sa.Column("room_number", sa.String(40), nullable=True),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("attended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'attended')", name="issue_status"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("customer_id", "router_id", "status"):
        op.create_index(f"ix_support_issues_{column}", "support_issues", [column])
    op.create_table(
        "support_issue_replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["support_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_issue_replies_issue_id", "support_issue_replies", ["issue_id"])


def downgrade() -> None:
    op.drop_table("support_issue_replies")
    op.drop_table("support_issues")
