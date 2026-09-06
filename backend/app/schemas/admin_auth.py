from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.models.enums import AdminRole

ADMIN_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def normalize_admin_username(value: str) -> str:
    return value.strip().lower()


class AdminLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str
    password: SecretStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = normalize_admin_username(value)
        if not ADMIN_USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid admin username.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not 8 <= len(password) <= 128:
            raise ValueError("Enter a valid admin password.")
        return value


class AuthenticatedAdminResponse(BaseModel):
    username: str
    role: AdminRole
    redirect_to: str = "/"


class AdminLogoutResponse(BaseModel):
    logged_out: bool = True
