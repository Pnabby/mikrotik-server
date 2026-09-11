"""add hostel plan groups

Revision ID: 20260911_0011
Revises: 20260911_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260911_0011"
down_revision: str | Sequence[str] | None = "20260911_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_groups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("router_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sort_by_price", sa.Boolean(), server_default="false", nullable=False),
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
        sa.CheckConstraint(
            "display_order >= 0", name=op.f("ck_plan_groups_plan_group_display_order_non_negative")
        ),
        sa.ForeignKeyConstraint(["router_id"], ["routers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("router_id", "name", name="uq_plan_group_router_name"),
    )
    op.create_index("ix_plan_groups_router_id", "plan_groups", ["router_id"])
    with op.batch_alter_table("router_package_profiles") as batch_op:
        batch_op.add_column(sa.Column("group_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_router_package_profiles_group_id_plan_groups",
            "plan_groups",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_router_package_profiles_group_id", ["group_id"])


def downgrade() -> None:
    with op.batch_alter_table("router_package_profiles") as batch_op:
        batch_op.drop_index("ix_router_package_profiles_group_id")
        batch_op.drop_constraint(
            "fk_router_package_profiles_group_id_plan_groups", type_="foreignkey"
        )
        batch_op.drop_column("group_id")
    op.drop_table("plan_groups")
