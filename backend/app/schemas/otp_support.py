from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.enums import OtpFlow
from app.schemas.account import normalize_recovery_identifier


class OtpUsageResponse(BaseModel):
    flow: OtpFlow
    subject: str
    customer_id: uuid.UUID | None
    username: str | None
    email: str | None
    phone_number: str | None
    requests_used: int
    request_limit: int
    requests_remaining: int
    last_requested_at: datetime | None
    next_request_at: datetime | None
    last_reset_at: datetime | None
    last_reset_by: str | None


class OtpSupportResponse(BaseModel):
    items: list[OtpUsageResponse]
    checked_at: datetime
    can_reset: bool


class OtpLimitResetRequest(BaseModel):
    flow: OtpFlow
    subject: str = Field(max_length=384)

    @model_validator(mode="after")
    def normalize_subject(self) -> OtpLimitResetRequest:
        if self.flow == OtpFlow.PHONE_VERIFICATION:
            if not self.subject.startswith("customer:"):
                raise ValueError("A customer is required for phone verification.")
            self.subject = f"customer:{uuid.UUID(self.subject[9:])}"
        else:
            if not self.subject.startswith("email:"):
                raise ValueError("An OTP destination is required.")
            self.subject = f"email:{normalize_recovery_identifier(self.subject[6:])}"
        return self
