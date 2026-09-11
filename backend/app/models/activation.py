from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ActivationStatus, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation_attempt import ActivationAttempt
    from app.models.customer import Customer
    from app.models.package import Package
    from app.models.router import Router
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


def new_activation_id() -> str:
    return f"ACT-{uuid.uuid4().hex.upper()}"


class Activation(TimestampMixin, Base):
    __tablename__ = "activations"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="activation_attempt_count_non_negative"),
        CheckConstraint(
            "char_length(target_profile) > 0", name="activation_target_profile_not_blank"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    activation_id: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, default=new_activation_id
    )
    # This monotonic receipt lets reconciliation distinguish known older/newer markers.
    sequence_number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, index=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT"), unique=True, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="RESTRICT"), index=True
    )
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="RESTRICT"), index=True
    )
    target_profile: Mapped[str] = mapped_column(String(120))
    target_disabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[ActivationStatus] = mapped_column(
        enum_type(ActivationStatus, "activation_status"),
        default=ActivationStatus.NOT_STARTED,
        server_default=ActivationStatus.NOT_STARTED.value,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sms_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activations.id", ondelete="SET NULL"), index=True
    )

    transaction: Mapped[Transaction] = relationship(back_populates="activation")
    customer: Mapped[Customer] = relationship(back_populates="activations")
    package: Mapped[Package] = relationship(back_populates="activations")
    router: Mapped[Router] = relationship(back_populates="activations")
    attempts: Mapped[list[ActivationAttempt]] = relationship(
        back_populates="activation", cascade="all, delete-orphan"
    )
    subscription: Mapped[Subscription | None] = relationship(
        back_populates="activation", uselist=False
    )
    superseded_by: Mapped[Activation | None] = relationship(
        remote_side="Activation.id", foreign_keys=[superseded_by_id]
    )
