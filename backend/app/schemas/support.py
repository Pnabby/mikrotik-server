from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PHONE_CHARACTERS = re.compile(r"^[+0-9()\- .]+$")
_WHATSAPP_HOSTS = {"wa.me", "api.whatsapp.com", "web.whatsapp.com"}


class SupportSettingsResponse(BaseModel):
    phone_number: str | None
    whatsapp_url: str | None


class SupportSettingsUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    phone_number: str | None = Field(default=None, max_length=40)
    whatsapp_url: str | None = Field(default=None, max_length=500)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = " ".join(value.split())
        if not _PHONE_CHARACTERS.fullmatch(normalized):
            raise ValueError("Enter a valid support phone number.")
        if "+" in normalized and (not normalized.startswith("+") or normalized.count("+") > 1):
            raise ValueError("Enter a valid support phone number.")
        digits = re.sub(r"\D", "", normalized)
        if not 7 <= len(digits) <= 15:
            raise ValueError("Enter a valid support phone number.")
        return normalized

    @field_validator("whatsapp_url")
    @classmethod
    def validate_whatsapp_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value if "://" in value else f"https://{value}"
        parsed = urlsplit(normalized)
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in _WHATSAPP_HOSTS:
            raise ValueError("Enter an official HTTPS WhatsApp link.")
        if parsed.username or parsed.password:
            raise ValueError("Enter an official HTTPS WhatsApp link.")
        return normalized
