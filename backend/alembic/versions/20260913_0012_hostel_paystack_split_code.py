"""add hostel Paystack split codes

Revision ID: 20260913_0012
Revises: 20260911_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260913_0012"
down_revision: str | Sequence[str] | None = "20260911_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "routers",
        sa.Column("paystack_split_code", sa.String(length=120), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_routers_router_paystack_split_code_not_blank"),
        "routers",
        "paystack_split_code IS NULL OR char_length(paystack_split_code) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_routers_router_paystack_split_code_not_blank"),
        "routers",
        type_="check",
    )
    op.drop_column("routers", "paystack_split_code")
