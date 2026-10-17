import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models.customer import Customer
from app.models.email_otp_challenge import EmailOtpChallenge
from app.routes import registration


@pytest.fixture
def signup_client(support_db, monkeypatch):
    session, _, _, source, _ = support_db
    source.hotspot_network = "10.10.0.0/16"
    session.commit()
    settings = Settings(
        _env_file=None,
        mnotify_api_key="test-sms-key",
        mnotify_sender_id="VladWiFi",
        otp_hash_secret="secure-registration-test-key-at-least-32-characters",
    )
    response_payload = {
        "status": "success", "code": "2000",
        "summary": {"_id": "campaign-test", "total_sent": 1, "total_rejected": 0},
    }
    sent_requests = []

    def post(url, **kwargs):
        sent_requests.append(kwargs["json"])
        if kwargs["json"].get("sms_type") == "otp":
            return httpx.Response(403, json={
                "status": "error",
                "error": "Sender ID is approved for SMS but is not registered as an OTP sender ID.",
            }, request=httpx.Request("POST", url))
        return httpx.Response(200, json=response_payload, request=httpx.Request("POST", url))

    monkeypatch.setattr("app.integrations.mnotify.client.httpx.post", post)
    router_users = {}
    router = Mock()
    router.get_hotspot_user_profile.return_value = {"name": "disabled"}
    router.get_hotspot_user.side_effect = lambda username: router_users.get(username)

    def create_user(**values):
        router_users[values["username"]] = {"name": values["username"], **values}

    router.create_hotspot_user.side_effect = create_user
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[registration.get_registration_router_client_factory] = lambda: lambda _: router
    app.dependency_overrides[registration.get_pin_hasher] = lambda: Mock(hash=Mock(return_value="hashed"))
    try:
        yield TestClient(app), session, sent_requests, response_payload
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def details(phone_number="024 123 4567"):
    return {"email": "newsignup@example.com", "phone_number": phone_number,
            "username": "newsignup", "router_id": "main", "pin": "123456", "accepted_terms": True}


@pytest.mark.parametrize("phone", ["024 123 4567", "024-123-4567", "233241234567", "+233241234567"])
def test_signup_sends_otp_to_normalized_phone_then_verifies_it(signup_client, phone):
    client, session, sent, _ = signup_client
    request = details(phone)
    started = client.post("/api/registration/start", json=request)
    assert started.status_code == 201, started.text
    assert len(sent) == 1
    assert sent[0]["recipient"] == ["233241234567"]
    assert "sms_type" not in sent[0]
    assert request["email"] not in sent[0]["message"]
    code = re.search(r"\b[0-9]{6}\b", sent[0]["message"]).group()
    payload = {**request, "challenge_id": started.json()["challenge_id"], "code": code}
    assert client.post("/api/registration/complete", json={**payload, "phone_number": "0207654321"}).status_code == 400
    completed = client.post("/api/registration/complete", json=payload)
    assert completed.status_code == 200, completed.text
    customer = session.scalar(select(Customer).where(Customer.username == "newsignup"))
    assert customer.phone_number == "+233241234567"
    assert customer.phone_verified_at is not None
    assert customer.email_verified_at is None


def test_signup_does_not_report_sent_when_provider_rejects_phone(signup_client):
    client, session, _, response_payload = signup_client
    response_payload["summary"]["total_sent"] = 0
    response_payload["summary"]["total_rejected"] = 1
    response = client.post("/api/registration/start", json=details())
    assert response.status_code == 503
    assert response.json()["code"] == "registration_sms_unavailable"
    challenge = session.scalar(select(EmailOtpChallenge))
    assert challenge.consumed_at is not None
    assert session.scalar(select(Customer).where(Customer.username == "newsignup")) is None


def test_failed_resend_keeps_previous_code_valid(signup_client):
    client, session, sent, response_payload = signup_client
    started = client.post("/api/registration/start", json=details())
    assert started.status_code == 201
    code = re.search(r"\b[0-9]{6}\b", sent[0]["message"]).group()
    challenge = session.scalar(select(EmailOtpChallenge))
    challenge.created_at = datetime.now(UTC) - timedelta(minutes=2)
    session.commit()
    response_payload["summary"]["total_sent"] = 0
    assert client.post("/api/registration/start", json=details()).status_code == 503
    session.refresh(challenge)
    assert challenge.consumed_at is None
    completed = client.post("/api/registration/complete", json={
        **details(), "challenge_id": started.json()["challenge_id"], "code": code,
    })
    assert completed.status_code == 200, completed.text


def test_successful_resend_replaces_previous_code(signup_client):
    client, session, sent, _ = signup_client
    first = client.post("/api/registration/start", json=details())
    old_code = re.search(r"\b[0-9]{6}\b", sent[0]["message"]).group()
    old = session.scalar(select(EmailOtpChallenge))
    old.created_at = datetime.now(UTC) - timedelta(minutes=2)
    session.commit()
    latest = client.post("/api/registration/start", json=details())
    assert latest.status_code == 201, latest.text
    session.refresh(old)
    assert old.consumed_at is not None
    assert client.post("/api/registration/complete", json={
        **details(), "challenge_id": first.json()["challenge_id"], "code": old_code,
    }).status_code == 400
    new_code = re.search(r"\b[0-9]{6}\b", sent[-1]["message"]).group()
    completed = client.post("/api/registration/complete", json={
        **details(), "challenge_id": latest.json()["challenge_id"], "code": new_code,
    })
    assert completed.status_code == 200, completed.text
