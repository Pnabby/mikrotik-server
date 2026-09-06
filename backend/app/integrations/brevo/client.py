from __future__ import annotations

from html import escape
from typing import Protocol

import httpx

from app.core.config import Settings


class EmailDeliveryError(RuntimeError):
    """Raised when an OTP email cannot be accepted by the provider."""


class OtpEmailSender(Protocol):
    def send_registration_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None: ...


class BrevoEmailSender:
    """Small, secret-safe adapter around Brevo's transactional email API."""

    def __init__(
        self,
        *,
        api_key: str,
        sender_email: str,
        sender_name: str,
        api_url: str = "https://api.brevo.com/v3",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender_email = sender_email
        self._sender_name = sender_name
        self._api_url = api_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> BrevoEmailSender:
        if settings.brevo_api_key is None or not settings.brevo_sender_email:
            raise EmailDeliveryError("Brevo transactional email is not configured.")
        return cls(
            api_key=settings.brevo_api_key.get_secret_value(),
            sender_email=settings.brevo_sender_email.strip(),
            sender_name=settings.brevo_sender_name.strip() or "Flint WiFi",
            api_url=settings.brevo_api_url,
            timeout_seconds=settings.brevo_timeout_seconds,
        )

    def send_registration_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        safe_code = escape(code)
        expiry_copy = f"{expires_in_minutes} minute" + (
            "" if expires_in_minutes == 1 else "s"
        )
        payload = {
            "sender": {"name": self._sender_name, "email": self._sender_email},
            "to": [{"email": recipient}],
            "subject": "Your Flint WiFi verification code",
            "textContent": (
                f"Your Flint WiFi verification code is {code}. "
                f"It expires in {expiry_copy}. If you did not request it, ignore this email."
            ),
            "htmlContent": (
                "<!doctype html><html><body style=\"font-family:Arial,sans-serif;"
                "color:#212529\"><div style=\"max-width:520px;margin:0 auto;padding:24px\">"
                "<h1 style=\"color:#4361ee;font-size:24px\">Verify your email</h1>"
                "<p>Enter this code to continue creating your Flint WiFi account:</p>"
                f"<p style=\"font-size:32px;font-weight:700;letter-spacing:8px\">{safe_code}</p>"
                f"<p>This code expires in {expiry_copy}.</p>"
                "<p style=\"color:#6c757d;font-size:13px\">If you did not request this "
                "code, you can safely ignore this email.</p></div></body></html>"
            ),
        }

        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    f"{self._api_url}/smtp/email",
                    headers={
                        "accept": "application/json",
                        "api-key": self._api_key,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            # Do not attach provider response bodies: they can contain recipient data.
            raise EmailDeliveryError("Brevo did not accept the OTP email.") from exc
