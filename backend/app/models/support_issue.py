from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SupportIssue(TimestampMixin, Base):
    __tablename__ = "support_issues"
    __table_args__ = (CheckConstraint("status IN ('open', 'attended')", name="issue_status"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    router_id: Mapped[str | None] = mapped_column(
        ForeignKey("routers.id", ondelete="SET NULL"), index=True
    )
    # Snapshot the origin so moving accounts or renaming hostels cannot rewrite a complaint.
    username: Mapped[str] = mapped_column(String(64))
    hostel_name: Mapped[str] = mapped_column(String(120))
    room_number: Mapped[str | None] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open", index=True
    )
    attended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replies: Mapped[list[SupportIssueReply]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
        order_by="SupportIssueReply.created_at",
    )


class SupportIssueReply(TimestampMixin, Base):
    __tablename__ = "support_issue_replies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("support_issues.id", ondelete="CASCADE"), index=True
    )
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    message: Mapped[str] = mapped_column(Text)
    issue: Mapped[SupportIssue] = relationship(back_populates="replies")
