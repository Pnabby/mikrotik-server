from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings


class SmsDeliveryError(RuntimeError):
    pass


class SmsSender(Protocol):
    def send(self, *, recipient: str, message: str) -> None: ...

    def send_verification_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None: ...


class MNotifySmsSender:
    def __init__(self, *, api_url: str, api_key: str, sender_id: str, timeout: float) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._sender_id = sender_id
        self._timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> MNotifySmsSender:
        if not settings.mnotify_api_key or not settings.mnotify_sender_id:
            raise SmsDeliveryError("mNotify is not configured.")
        return cls(
            api_url=settings.mnotify_api_url,
            api_key=settings.mnotify_api_key.get_secret_value(),
            sender_id=settings.mnotify_sender_id,
            timeout=settings.mnotify_timeout_seconds,
        )

    def send_verification_otp(self, *, recipient: str, code: str, expires_in_minutes: int) -> None:
        self.send(
            recipient=recipient,
            message=(
                f"Your Flint WiFi verification code is {code}. "
                f"It expires in {expires_in_minutes} minutes."
            ),
        )

    def send(self, *, recipient: str, message: str) -> None:
        try:
            response = httpx.post(
                self._api_url,
                params={"key": self._api_key},
                json={
                    "recipient": [recipient.lstrip("+")],
                    "sender": self._sender_id,
                    "message": message,
                    "is_schedule": False,
                    "schedule_date": "",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if str(payload.get("status", "success")).lower() in {"error", "failed", "false"}:
                raise SmsDeliveryError("mNotify rejected the message.")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise SmsDeliveryError("SMS could not be sent.") from exc
