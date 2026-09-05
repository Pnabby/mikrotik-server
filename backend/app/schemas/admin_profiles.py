from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import RouterStatus


class AdminHostelSummary(BaseModel):
    router_id: str
    name: str
    location: str | None
    status: RouterStatus
    is_active: bool
    last_seen_at: datetime | None
    configured_profiles: int
    published_profiles: int


class AdminRouterProfileResponse(BaseModel):
    mikrotik_profile: str
    display_name: str | None
    description: str | None
    package_id: uuid.UUID | None
    amount: Decimal | None
    currency: str
    duration_seconds: int | None
    data_limit_bytes: int | None
    device_limit: int | None
    download_speed: str | None
    is_configured: bool
    is_visible: bool
    is_registration_profile: bool
    available_on_router: bool
    rate_limit: str | None
    shared_users: int | None
    session_timeout: str | None
    idle_timeout: str | None
    address_pool: str | None


class AdminProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    display_name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="GHS", min_length=3, max_length=3)
    duration_seconds: int | None = Field(default=None, gt=0, le=10 * 365 * 24 * 60 * 60)
    data_limit_bytes: int | None = Field(default=None, gt=0)
    device_limit: int | None = Field(default=None, gt=0, le=100)
    download_speed: str | None = Field(default=None, max_length=40)
    is_visible: bool = False

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Enter a display name.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        normalized = " ".join(value.split()) if value else ""
        return normalized or None

    @field_validator("download_speed")
    @classmethod
    def normalize_download_speed(cls, value: str | None) -> str | None:
        normalized = " ".join(value.split()) if value else ""
        return normalized or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.isalpha():
            raise ValueError("Enter a valid three-letter currency code.")
        return normalized
