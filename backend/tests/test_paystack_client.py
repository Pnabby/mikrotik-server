from __future__ import annotations

import json

import httpx
import pytest

from app.integrations.paystack import PaystackClient, PaystackError


def test_paystack_client_initializes_checkout_with_server_secret() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/access-code",
                    "access_code": "access-code",
                    "reference": "FLINT-123",
                },
            },
        )

    client = PaystackClient(
        secret_key="sk_test_private",
        transport=httpx.MockTransport(handler),
    )
    initialized = client.initialize_transaction(
        email="ama@example.com",
        amount=2500,
        currency="GHS",
        reference="FLINT-123",
        callback_url="https://example.com/api/payments/paystack/callback",
        metadata={"customer_id": "customer-1"},
    )

    assert initialized.authorization_url == "https://checkout.paystack.com/access-code"
    assert captured["authorization"] == "Bearer sk_test_private"
    assert captured["payload"] == {
        "email": "ama@example.com",
        "amount": "2500",
        "currency": "GHS",
        "reference": "FLINT-123",
        "callback_url": "https://example.com/api/payments/paystack/callback",
        "metadata": {"customer_id": "customer-1"},
    }


def test_paystack_client_verifies_provider_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/transaction/verify/FLINT-123"
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "reference": "FLINT-123",
                    "status": "success",
                    "amount": 2500,
                    "currency": "GHS",
                    "paid_at": "2026-09-05T12:00:00Z",
                    "customer": {"email": "AMA@example.com"},
                    "metadata": {"customer_id": "customer-1"},
                },
            },
        )

    verified = PaystackClient(
        secret_key="sk_test_private",
        transport=httpx.MockTransport(handler),
    ).verify_transaction("FLINT-123")

    assert verified.status == "success"
    assert verified.amount == 2500
    assert verified.customer_email == "ama@example.com"
    assert verified.paid_at is not None


def test_paystack_client_rejects_untrusted_checkout_url() -> None:
    client = PaystackClient(
        secret_key="sk_test_private",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "status": True,
                    "data": {
                        "authorization_url": "https://example.com/fake-checkout",
                        "access_code": "access-code",
                        "reference": "FLINT-123",
                    },
                },
            )
        ),
    )

    with pytest.raises(PaystackError):
        client.initialize_transaction(
            email="ama@example.com",
            amount=2500,
            currency="GHS",
            reference="FLINT-123",
            callback_url="https://example.com/callback",
            metadata={},
        )
