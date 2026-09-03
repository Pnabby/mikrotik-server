from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PaymentStatus, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation import Activation
    from app.models.customer import Customer
    from app.models.package import Package
    from app.models.payment_event import PaymentEvent
    from app.models.router import Router
    from app.models.subscription import Subscription


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="transaction_amount_non_negative"),
        CheckConstraint(
            "char_length(currency) = 3 AND currency = upper(currency)",
            name="transaction_currency_iso_code",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="RESTRICT"), index=True
    )
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="RESTRICT"), index=True
    )
    paystack_reference: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="GHS", server_default="GHS")
    payment_status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )
    provider_status: Mapped[str | None] = mapped_column(String(80))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship(back_populates="transactions")
    package: Mapped[Package] = relationship(back_populates="transactions")
    router: Mapped[Router] = relationship(back_populates="transactions")
    payment_events: Mapped[list[PaymentEvent]] = relationship(back_populates="transaction")
    activation: Mapped[Activation | None] = relationship(
        back_populates="transaction", uselist=False
    )
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="transaction", uselist=False
    )
