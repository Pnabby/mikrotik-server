from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AdminRole, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.admin_session import AdminSession
    from app.models.audit_log import AuditLog


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="admin_email_normalized"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole] = mapped_column(
        enum_type(AdminRole, "admin_role"),
        default=AdminRole.VIEWER,
        server_default=AdminRole.VIEWER.value,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="admin_user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="admin_user")
