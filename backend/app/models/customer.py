from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AccountStatus, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.activation import Activation
    from app.models.customer_session import CustomerSession
    from app.models.email_otp_challenge import EmailOtpChallenge
    from app.models.router import Router
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="customer_email_normalized"),
        CheckConstraint("username = lower(username)", name="customer_username_normalized"),
        CheckConstraint("char_length(username) >= 3", name="customer_username_min_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="RESTRICT"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Only a password-hasher output belongs here; plaintext PINs must never be persisted.
    pin_hash: Mapped[str] = mapped_column(String(255))
    account_status: Mapped[AccountStatus] = mapped_column(
        enum_type(AccountStatus, "account_status"),
        default=AccountStatus.INACTIVE,
        server_default=AccountStatus.INACTIVE.value,
        index=True,
    )
    email_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mikrotik_user_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    router: Mapped[Router] = relationship(back_populates="customers")
    otp_challenges: Mapped[list[EmailOtpChallenge]] = relationship(back_populates="customer")
    sessions: Mapped[list[CustomerSession]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    transactions: Mapped[list[Transaction]] = relationship(back_populates="customer")
    activations: Mapped[list[Activation]] = relationship(back_populates="customer")
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="customer")
