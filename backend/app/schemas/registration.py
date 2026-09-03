from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
PIN_PATTERN = re.compile(r"^[0-9]{6}$")


class RegistrationStartRequest(BaseModel):
    """Contract for the upcoming email-OTP registration endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    username: str
    router_id: str
    pin: SecretStr

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
        normalized = value.casefold()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("Username format is invalid.")
        return normalized

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
