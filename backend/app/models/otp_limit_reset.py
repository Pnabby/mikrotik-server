from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OtpLimitReset(Base):
    __tablename__ = "otp_limit_resets"
    __table_args__ = (Index("ix_otp_limit_resets_scope", "flow", "subject", "reset_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flow: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(384))
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    admin_email: Mapped[str] = mapped_column(String(320))
    reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
