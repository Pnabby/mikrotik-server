from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation import Activation
    from app.models.router import Router
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


class Package(TimestampMixin, Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="package_amount_non_negative"),
        CheckConstraint("duration_seconds > 0", name="package_duration_positive"),
        CheckConstraint(
            "data_limit_bytes IS NULL OR data_limit_bytes > 0",
            name="package_data_limit_positive",
        ),
        CheckConstraint(
            "device_limit IS NULL OR device_limit > 0",
            name="package_device_limit_positive",
        ),
        CheckConstraint(
            "char_length(currency) = 3 AND currency = upper(currency)",
            name="package_currency_iso_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="GHS", server_default="GHS")
    duration_seconds: Mapped[int] = mapped_column(BigInteger)
    data_limit_bytes: Mapped[int | None] = mapped_column(BigInteger)
    device_limit: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    router_profiles: Mapped[list[RouterPackageProfile]] = relationship(
        back_populates="package", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(back_populates="package")
    activations: Mapped[list[Activation]] = relationship(back_populates="package")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="package")


class RouterPackageProfile(TimestampMixin, Base):
    __tablename__ = "router_package_profiles"
    __table_args__ = (
        UniqueConstraint("router_id", "package_id", name="uq_router_package_profile"),
        UniqueConstraint("router_id", "mikrotik_profile", name="uq_router_mikrotik_profile"),
        CheckConstraint(
            "char_length(mikrotik_profile) > 0",
            name="mikrotik_profile_not_blank",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id", ondelete="CASCADE"), index=True)
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True
    )
    mikrotik_profile: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    router: Mapped[Router] = relationship(back_populates="package_profiles")
    package: Mapped[Package] = relationship(back_populates="router_profiles")
