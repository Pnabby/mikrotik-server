from __future__ import annotations

import logging
import re
from typing import Protocol

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class SmsDeliveryError(RuntimeError):
    pass


class SmsSender(Protocol):
    def send(self, *, recipient: str, message: str) -> None: ...

    def send_verification_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None: ...

    def send_pin_reset_otp(
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
        self._send(
            recipient=recipient,
            message=(
                f"Your Vlad WiFi verification code is {code}. "
                f"It expires in {expires_in_minutes} minutes."
            ),
            sms_type="otp",
        )

    def send_pin_reset_otp(self, *, recipient: str, code: str, expires_in_minutes: int) -> None:
        self._send(
            recipient=recipient,
            message=(
                f"Your Vlad WiFi PIN reset code is {code}. "
                f"It expires in {expires_in_minutes} minutes."
            ),
            sms_type="otp",
        )

    def send(self, *, recipient: str, message: str) -> None:
        self._send(recipient=recipient, message=message)

    def _send(self, *, recipient: str, message: str, sms_type: str | None = None) -> None:
        request_body = {
            "recipient": [recipient.lstrip("+")],
            "sender": self._sender_id,
            "message": message,
            "is_schedule": False,
            "schedule_date": "",
        }
        if sms_type is not None:
            request_body["sms_type"] = sms_type
        try:
            response = httpx.post(
                self._api_url,
                params={"key": self._api_key},
                json=request_body,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            # HTTP exceptions can include the API key in the request URL. Keep them
            # out of caller tracebacks and never log message bodies or OTPs.
            logger.warning("mNotify SMS request failed; failure_type=%s", type(exc).__name__)
            raise SmsDeliveryError("SMS could not be sent.") from None

        if not isinstance(payload, dict):
            logger.warning("mNotify returned an invalid SMS response")
            raise SmsDeliveryError("SMS acceptance could not be confirmed.")

        provider_code = str(payload.get("code", ""))
        if str(payload.get("status", "")).lower() != "success" or provider_code != "2000":
            logger.warning(
                "mNotify rejected SMS; provider_code=%s",
                provider_code if re.fullmatch(r"[0-9]{1,8}", provider_code) else "unknown",
            )
            raise SmsDeliveryError("mNotify rejected the message.")

        summary = payload.get("summary")
        if not isinstance(summary, dict):
            logger.warning("mNotify SMS response has no acceptance summary")
            raise SmsDeliveryError("SMS acceptance could not be confirmed.")
        if str(summary.get("total_sent")) != "1" or str(summary.get("total_rejected")) != "0":
            logger.warning("mNotify did not accept the SMS recipient")
            raise SmsDeliveryError("mNotify did not accept the SMS recipient.")

        campaign_id = str(summary.get("_id", ""))
        logger.info(
            "mNotify accepted SMS; campaign_id=%s; sms_type=%s",
            campaign_id if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", campaign_id) else "unknown",
            sms_type or "standard",
        )
