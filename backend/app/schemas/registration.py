from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.models.enums import AccountStatus

USERNAME_PATTERN = re.compile(r"^[a-z0-9]{3,64}$")
PIN_PATTERN = re.compile(r"^[0-9]{6}$")
TERMS_VERSION = "2026-09-05"
PRIVACY_NOTICE_VERSION = "2026-09-05"


def normalize_username(value: str) -> str:
    normalized = value.strip().casefold()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("Username format is invalid.")
    return normalized


class RegistrationStartRequest(BaseModel):
    """Account details validated before a registration OTP is sent."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    username: str
    router_id: str
    pin: SecretStr
    accepted_terms: bool

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.casefold()
        local, separator, domain = normalized.partition("@")
        if (
            not separator
            or not local
            or "." not in domain
            or domain.startswith(".")
            or domain.endswith(".")
            or len(normalized) > 320
        ):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("router_id")
    @classmethod
    def require_router_id(cls, value: str) -> str:
        if not value:
            raise ValueError("A hostel is required.")
        return value

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("PIN must contain exactly 6 digits.")
        return value

    @field_validator("accepted_terms")
    @classmethod
    def require_terms_acceptance(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must accept the Terms and Conditions.")
        return value


class RegistrationStartResponse(BaseModel):
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


class UsernameAvailabilityResponse(BaseModel):
    username: str
    available: bool
    suggestions: list[str]


class RegistrationRouterReadinessResponse(BaseModel):
    router_id: str
    username: str
    ready: bool


class RegistrationCompleteRequest(RegistrationStartRequest):
    challenge_id: uuid.UUID
    code: SecretStr

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Verification code must contain exactly 6 digits.")
        return value


class RegistrationCompleteResponse(BaseModel):
    customer_id: uuid.UUID
    username: str
    account_status: AccountStatus
    router_user_disabled: bool
