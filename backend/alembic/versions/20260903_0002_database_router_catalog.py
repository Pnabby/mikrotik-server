"""store complete router catalogue metadata in the database

Revision ID: 20260903_0002
Revises: 20260902_0001
Create Date: 2026-09-03 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260903_0002"
down_revision: str | Sequence[str] | None = "20260902_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "routers",
        sa.Column("api_port", sa.Integer(), server_default="8728", nullable=False),
    )
    op.add_column(
        "routers",
        sa.Column("hotspot_network", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "routers",
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_routers_router_api_port_valid"),
        "routers",
        "api_port > 0 AND api_port <= 65535",
    )
    op.create_check_constraint(
        op.f("ck_routers_router_hotspot_network_not_blank"),
        "routers",
        "hotspot_network IS NULL OR char_length(hotspot_network) > 0",
    )
    op.create_check_constraint(
        op.f("ck_routers_router_display_order_non_negative"),
        "routers",
        "display_order >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_routers_router_display_order_non_negative"),
        "routers",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_routers_router_hotspot_network_not_blank"),
        "routers",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_routers_router_api_port_valid"),
        "routers",
        type_="check",
    )
    op.drop_column("routers", "display_order")
    op.drop_column("routers", "hotspot_network")
    op.drop_column("routers", "api_port")
