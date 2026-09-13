from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import Settings


class PaystackError(RuntimeError):
    """Raised when Paystack cannot provide a trustworthy payment result."""


@dataclass(frozen=True, slots=True)
class InitializedTransaction:
    authorization_url: str
    access_code: str
    reference: str


@dataclass(frozen=True, slots=True)
class VerifiedTransaction:
    reference: str
    status: str
    amount: int
    currency: str
    paid_at: datetime | None
    customer_email: str | None
    metadata: dict[str, object]


class PaystackGateway(Protocol):
    def initialize_transaction(
        self,
        *,
        email: str,
        amount: int,
        currency: str,
        reference: str,
        callback_url: str,
        metadata: dict[str, object],
        split_code: str | None = None,
    ) -> InitializedTransaction: ...

    def verify_transaction(self, reference: str) -> VerifiedTransaction: ...


class PaystackClient:
    """Secret-safe adapter for Paystack's server-side transaction API."""

    def __init__(
        self,
        *,
        secret_key: str,
        api_url: str = "https://api.paystack.co",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._secret_key = secret_key
        self._api_url = api_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> PaystackClient:
        if settings.paystack_secret_key is None:
            raise PaystackError("Paystack is not configured.")
        secret_key = settings.paystack_secret_key.get_secret_value().strip()
        if not secret_key.startswith(("sk_test_", "sk_live_")):
            raise PaystackError("Paystack is not configured.")
        return cls(
            secret_key=secret_key,
            api_url=settings.paystack_api_url,
            timeout_seconds=settings.paystack_timeout_seconds,
        )

    def initialize_transaction(
        self,
        *,
        email: str,
        amount: int,
        currency: str,
        reference: str,
        callback_url: str,
        metadata: dict[str, object],
        split_code: str | None = None,
    ) -> InitializedTransaction:
        request_payload: dict[str, object] = {
            "email": email,
            "amount": str(amount),
            "currency": currency,
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        normalized_split_code = (split_code or "").strip()
        if normalized_split_code:
            request_payload["split_code"] = normalized_split_code
        payload = self._request(
            "POST",
            "/transaction/initialize",
            json=request_payload,
        )
        data = _response_data(payload)
        authorization_url = _text(data.get("authorization_url"))
        access_code = _text(data.get("access_code"))
        returned_reference = _text(data.get("reference"))
        parsed_url = urlparse(authorization_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "checkout.paystack.com"
            or not access_code
            or returned_reference != reference
        ):
            raise PaystackError("Paystack returned an invalid checkout response.")
        return InitializedTransaction(
            authorization_url=authorization_url,
            access_code=access_code,
            reference=returned_reference,
        )

    def verify_transaction(self, reference: str) -> VerifiedTransaction:
        payload = self._request("GET", f"/transaction/verify/{reference}")
        data = _response_data(payload)
        returned_reference = _text(data.get("reference"))
        provider_status = _text(data.get("status")).casefold()
        amount = data.get("amount")
        currency = _text(data.get("currency")).upper()
        if returned_reference != reference or not provider_status or not isinstance(amount, int):
            raise PaystackError("Paystack returned an invalid verification response.")
        customer = data.get("customer")
        customer_email = (
            _text(customer.get("email")).casefold() if isinstance(customer, dict) else None
        )
        metadata = data.get("metadata")
        return VerifiedTransaction(
            reference=returned_reference,
            status=provider_status,
            amount=amount,
            currency=currency,
            paid_at=_parse_datetime(data.get("paid_at")),
            customer_email=customer_email or None,
            metadata=metadata if isinstance(metadata, dict) else {},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            with httpx.Client(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    f"{self._api_url}{path}",
                    headers={
                        "Authorization": f"Bearer {self._secret_key}",
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=json,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            # Do not retain an httpx request object that contains the Authorization header.
            raise PaystackError("Paystack is temporarily unavailable.") from None
        if not isinstance(payload, dict) or payload.get("status") is not True:
            raise PaystackError("Paystack did not accept the request.")
        return payload


def paystack_is_configured(settings: Settings) -> bool:
    if settings.paystack_secret_key is None or not settings.paystack_callback_url:
        return False
    secret_key = settings.paystack_secret_key.get_secret_value().strip()
    callback = urlparse(settings.paystack_callback_url.strip())
    return secret_key.startswith(("sk_test_", "sk_live_")) and callback.scheme == "https"


def _response_data(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise PaystackError("Paystack returned an invalid response.")
    return data


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None
