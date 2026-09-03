from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PaymentEventStatus, enum_type

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )
    # A Paystack event ID or deterministic payload digest makes webhook handling idempotent.
    event_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    paystack_reference: Mapped[str | None] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[PaymentEventStatus] = mapped_column(
        enum_type(PaymentEventStatus, "payment_event_status"),
        default=PaymentEventStatus.RECEIVED,
        server_default=PaymentEventStatus.RECEIVED.value,
        index=True,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    processing_error: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transaction: Mapped[Transaction | None] = relationship(back_populates="payment_events")
