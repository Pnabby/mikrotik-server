from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import RouterStatus


class AdminHostelSummary(BaseModel):
    router_id: str
    name: str
    location: str | None
    vpn_host: str
    api_port: int
    hotspot_network: str | None
    display_order: int
    status: RouterStatus
    is_active: bool
    last_seen_at: datetime | None
    configured_profiles: int
    published_profiles: int


class AdminHostelUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    vpn_host: str = Field(min_length=1, max_length=255)
    api_port: int = Field(gt=0, le=65535)
    hotspot_network: str | None = Field(default=None, max_length=255)
    display_order: int = Field(ge=0)
    is_active: bool

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("location", "hotspot_network")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = " ".join(value.split()) if value else ""
        return normalized or None


class AdminHostelCreate(AdminHostelUpdate):
    router_id: str = Field(min_length=2, max_length=64)
    hotspot_network: str = Field(min_length=1, max_length=255)

    @field_validator("router_id")
    @classmethod
    def validate_router_id(cls, value: str) -> str:
        normalized = value.lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", normalized):
            raise ValueError("Enter a valid hostel ID.")
        return normalized

    @field_validator("hotspot_network")
    @classmethod
    def require_hotspot_network(cls, value: str) -> str:
        if not value:
            raise ValueError("Enter a hotspot network.")
        return value


class AdminRouterProfileResponse(BaseModel):
    mikrotik_profile: str
    display_name: str | None
    description: str | None
    package_id: uuid.UUID | None
    group_id: uuid.UUID | None
    amount: Decimal | None
    currency: str
    duration_seconds: int | None
    data_limit_bytes: int | None
    device_limit: int | None
    download_speed: str | None
    is_promotional: bool
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
    is_promotional: bool = False
    is_visible: bool = False
    group_id: uuid.UUID | None = None

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

    @model_validator(mode="after")
    def validate_free_public_plan(self) -> AdminProfileUpdate:
        if self.is_visible and self.amount == 0 and not self.is_promotional:
            raise ValueError("A published free plan must be promotional.")
        return self


class AdminPlanGroupCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    display_order: int = Field(default=0, ge=0)
    sort_by_price: bool = False
    profile_names: list[str] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("description")
    @classmethod
    def normalize_group_description(cls, value: str | None) -> str | None:
        normalized = " ".join(value.split()) if value else ""
        return normalized or None

    @field_validator("profile_names")
    @classmethod
    def normalize_profile_names(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            name = value.strip()
            if not name or len(name) > 120:
                raise ValueError("Each selected plan must have a valid profile name.")
            key = name.casefold()
            if key not in seen:
                normalized.append(name)
                seen.add(key)
        return normalized


class AdminPlanGroupUpdate(AdminPlanGroupCreate):
    pass


class AdminPlanGroupResponse(AdminPlanGroupCreate):
    id: uuid.UUID
    plan_count: int
