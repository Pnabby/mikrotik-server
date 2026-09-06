from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ActivationAttemptOutcome, ActivationTrigger, enum_type

if TYPE_CHECKING:
    from app.models.activation import Activation


class ActivationAttempt(Base):
    __tablename__ = "activation_attempts"
    __table_args__ = (
        UniqueConstraint("activation_id", "attempt_number", name="uq_activation_attempt_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    activation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activations.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[ActivationTrigger] = mapped_column(
        enum_type(ActivationTrigger, "activation_trigger"), index=True
    )
    outcome: Mapped[ActivationAttemptOutcome] = mapped_column(
        enum_type(ActivationAttemptOutcome, "activation_attempt_outcome"),
        default=ActivationAttemptOutcome.PROCESSING,
        server_default=ActivationAttemptOutcome.PROCESSING.value,
        index=True,
    )
    observed_activation_id: Mapped[str | None] = mapped_column(String(80))
    observed_profile: Mapped[str | None] = mapped_column(String(120))
    observed_disabled: Mapped[bool | None] = mapped_column(Boolean)
    router_state_before: Mapped[dict[str, object] | None] = mapped_column(JSON)
    router_state_after: Mapped[dict[str, object] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    activation: Mapped[Activation] = relationship(back_populates="attempts")
