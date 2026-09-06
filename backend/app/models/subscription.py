from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import SubscriptionStatus, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation import Activation
    from app.models.customer import Customer
    from app.models.package import Package
    from app.models.router import Router
    from app.models.transaction import Transaction


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "expires_at IS NULL OR starts_at IS NULL OR expires_at > starts_at",
            name="subscription_expiry_after_start",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="RESTRICT"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), unique=True, index=True
    )
    activation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activations.id", ondelete="RESTRICT"), unique=True, index=True
    )
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_type(SubscriptionStatus, "subscription_status"),
        default=SubscriptionStatus.PENDING,
        server_default=SubscriptionStatus.PENDING.value,
        index=True,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True
    )

    customer: Mapped[Customer] = relationship(back_populates="subscriptions")
    package: Mapped[Package] = relationship(back_populates="subscriptions")
    transaction: Mapped[Transaction] = relationship(back_populates="subscription")
    activation: Mapped[Activation] = relationship(back_populates="subscription")
    router: Mapped[Router] = relationship(back_populates="subscriptions")
    superseded_by: Mapped[Subscription | None] = relationship(
        remote_side="Subscription.id", foreign_keys=[superseded_by_id]
    )
