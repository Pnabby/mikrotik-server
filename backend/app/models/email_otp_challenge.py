from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OtpPurpose, enum_type

if TYPE_CHECKING:
    from app.models.customer import Customer


class EmailOtpChallenge(Base):
    __tablename__ = "email_otp_challenges"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="otp_email_normalized"),
        CheckConstraint("attempt_count >= 0", name="otp_attempt_count_non_negative"),
        CheckConstraint("max_attempts > 0", name="otp_max_attempts_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    phone_number: Mapped[str | None] = mapped_column(String(16), index=True)
    purpose: Mapped[OtpPurpose] = mapped_column(enum_type(OtpPurpose, "otp_purpose"), index=True)
    # Store only a keyed/one-way digest of the OTP, never the code itself.
    code_hash: Mapped[str] = mapped_column(String(255))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    customer: Mapped[Customer | None] = relationship(back_populates="otp_challenges")
