from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class HostelTransferOperation(TimestampMixin, Base):
    __tablename__ = "hostel_transfer_operations"
    __table_args__ = (
        CheckConstraint(
            "source_router_id <> destination_router_id", name="transfer_distinct_routers"
        ),
        CheckConstraint("attempt_count >= 0", name="transfer_attempts_non_negative"),
        CheckConstraint(
            "status IN ('running', 'reconciliation_required', 'manual_review', 'completed', 'rolled_back')",
            name="transfer_status",
        ),
        Index(
            "uq_hostel_transfer_active_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    source_router_id: Mapped[str] = mapped_column(ForeignKey("routers.id", ondelete="RESTRICT"))
    destination_router_id: Mapped[str] = mapped_column(
        ForeignKey("routers.id", ondelete="RESTRICT")
    )
    destination_router_name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="prepared")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Includes necessary RouterOS credentials, encrypted and authenticated as one envelope.
    encrypted_snapshot: Mapped[str | None] = mapped_column(Text)
    remaining_byte_limits: Mapped[dict[str, int | None] | None] = mapped_column(JSON)
    remaining_uptime_seconds: Mapped[int | None] = mapped_column(Integer)
    subscription_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_user_id: Mapped[str] = mapped_column(String(32))
    destination_user_id: Mapped[str | None] = mapped_column(String(32))
    last_confirmed_state: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_type: Mapped[str] = mapped_column(String(16))
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    ip_address: Mapped[str | None] = mapped_column(String(64))
