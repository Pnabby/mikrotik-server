from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RouterStatus, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation import Activation
    from app.models.customer import Customer
    from app.models.package import PlanGroup, RouterPackageProfile
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


class Router(TimestampMixin, Base):
    __tablename__ = "routers"
    __table_args__ = (
        CheckConstraint("char_length(id) > 0", name="router_id_not_blank"),
        CheckConstraint("char_length(name) > 0", name="router_name_not_blank"),
        CheckConstraint(
            "api_port > 0 AND api_port <= 65535",
            name="router_api_port_valid",
        ),
        CheckConstraint(
            "hotspot_network IS NULL OR char_length(hotspot_network) > 0",
            name="router_hotspot_network_not_blank",
        ),
        CheckConstraint("display_order >= 0", name="router_display_order_non_negative"),
    )

    # This stable ID is selected by customers and referenced by related records.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    vpn_host: Mapped[str] = mapped_column(String(255), unique=True)
    api_port: Mapped[int] = mapped_column(Integer, default=8728, server_default="8728")
    hotspot_network: Mapped[str | None] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[RouterStatus] = mapped_column(
        enum_type(RouterStatus, "router_status"),
        default=RouterStatus.UNKNOWN,
        server_default=RouterStatus.UNKNOWN.value,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customers: Mapped[list[Customer]] = relationship(back_populates="router")
    package_profiles: Mapped[list[RouterPackageProfile]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )
    plan_groups: Mapped[list[PlanGroup]] = relationship(
        back_populates="router", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(back_populates="router")
    activations: Mapped[list[Activation]] = relationship(back_populates="router")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="router")
