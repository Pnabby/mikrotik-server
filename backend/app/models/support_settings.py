from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class SupportSettings(TimestampMixin, Base):
    __tablename__ = "support_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="support_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    phone_number: Mapped[str | None] = mapped_column(String(40))
    whatsapp_url: Mapped[str | None] = mapped_column(String(500))
