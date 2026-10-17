import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.main import app
from app.models.audit_log import AuditLog
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import AdminRole, OtpFlow, OtpPurpose
from app.models.otp_limit_reset import OtpLimitReset
from app.models.phone_otp_challenge import PhoneOtpChallenge
from app.routes import auth, registration
from app.routes.admin_auth import get_authenticated_admin
from app.services.otp_limits import customer_subject, email_subject, enforce_otp_request_limit
from app.services.otp_support import OtpSupportService


@pytest.fixture
def otp_support_client(support_db, monkeypatch):
    session, customers, admin, source, _ = support_db
    source.hotspot_network = "10.10.0.0/16"
    customers[0].phone_number = "+233241234567"
    customers[0].phone_verified_at = datetime.now(UTC)
    settings = Settings(
        _env_file=None,
        otp_max_requests_per_hour=3,
        otp_max_attempts=2,
        otp_hash_secret="secure-otp-test-secret-at-least-32-characters",
        pin_hash_secret="secure-pin-test-secret-at-least-32-characters",
    )
    email_sender, sms_sender, router = Mock(), Mock(), Mock()
    router.get_hotspot_user_profile.return_value = {"name": "disabled"}
    router.get_hotspot_user.side_effect = lambda username: (
        {"name": username} if username in {"ama", "kwame"} else None
    )
    session.commit()
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_authenticated_admin] = lambda: admin
    app.dependency_overrides[auth.get_authenticated_customer] = lambda: customers[0]
    app.dependency_overrides[auth.get_password_email_sender] = lambda: email_sender
    app.dependency_overrides[auth.get_password_sms_sender] = lambda: sms_sender
    app.dependency_overrides[auth.get_password_router_factory] = lambda: lambda _: router
    app.dependency_overrides[registration.get_registration_sms_sender] = lambda: sms_sender
    app.dependency_overrides[registration.get_registration_router_client_factory] = lambda: (
        lambda _: router
    )
    monkeypatch.setattr(
        "app.services.phone_verification.MNotifySmsSender.from_settings", lambda _: sms_sender
    )
    try:
        yield TestClient(app), session, customers, admin, settings, email_sender, sms_sender
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def seed_requests(
    session, flow, email="ama@example.com", customer=None, phone="+233241234567", times=None
):
    now = datetime.now(UTC)
    times = times or [
        now - timedelta(minutes=3),
        now - timedelta(minutes=2),
        now - timedelta(seconds=20),
    ]
    rows = []
    for requested_at in times:
        values = dict(
            code_hash="private-test-otp-hash",
            attempt_count=2,
            max_attempts=2,
            expires_at=now + timedelta(minutes=10),
            created_at=requested_at,
            phone_number=phone,
            customer_id=customer.id if customer else None,
        )
        row = (
            PhoneOtpChallenge(**values)
            if flow == OtpFlow.PHONE_VERIFICATION
            else EmailOtpChallenge(**values, email=email, purpose=OtpPurpose(flow.value))
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


def lookup(client, contact):
    response = client.get("/api/admin/otp-support", params={"search": contact})
    assert response.status_code == 200, response.text
    return response.json()


def reset(client, flow, subject):
    return client.post(
        "/api/admin/otp-support/reset", json={"flow": flow.value, "subject": subject}
    )


def test_pending_signup_is_found_by_phone_or_email(otp_support_client):
    client, session, *_ = otp_support_client
    seed_requests(session, OtpFlow.REGISTRATION, email="new-signup@example.com")
    by_phone = lookup(client, "024 123 4567")
    by_email = lookup(client, " New-Signup@EXAMPLE.com ")
    for result in (by_phone, by_email):
        row = next(
            row
            for row in result["items"]
            if row["flow"] == "registration" and row["email"] == "new-signup@example.com"
        )
        assert row["customer_id"] is None
        assert row["email"] == "new-signup@example.com"
        assert row["requests_used"] == 3
        assert row["requests_remaining"] == 0
        assert row["next_request_at"]
        assert "private-test-otp-hash" not in str(result)


@pytest.mark.parametrize("flow", list(OtpFlow))
def test_reset_restores_actual_request_allowance_for_each_flow(otp_support_client, flow):
    client, session, customers, admin, settings, email_sender, sms_sender = otp_support_client
    customer = customers[0]
    if flow == OtpFlow.REGISTRATION:
        email = "newsignup@example.com"
        subject = email_subject(email)
        endpoint = "/api/registration/start"
        payload = dict(
            email=email,
            phone_number="0207654321",
            username="newsignup",
            pin="123456",
            router_id="main",
            accepted_terms=True,
        )
        owner = None
    else:
        email, owner = customer.email, customer
        subject = email_subject(email)
        if flow == OtpFlow.PHONE_VERIFICATION:
            customer.phone_verified_at = None
            subject = customer_subject(customer.id)
            endpoint, payload = (
                "/api/account/phone-verification/start",
                {"phone_number": customer.phone_number},
            )
        elif flow == OtpFlow.ACCOUNT_UNLOCK:
            customer.locked_at = datetime.now(UTC)
            endpoint, payload = "/api/auth/account-unlock/start", {"username": customer.username}
        else:
            endpoint = "/api/auth/" + flow.value.replace("_", "-") + "/start"
            payload = {"email": email}
    originals = seed_requests(session, flow, email=email, customer=owner)
    assert client.post(endpoint, json=payload).status_code == 429
    response = reset(client, flow, subject)
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored["requests_used"] == 0
    assert restored["requests_remaining"] == settings.otp_max_requests_per_hour
    assert restored["next_request_at"] is None
    assert restored["last_reset_by"] == admin.email
    email_sender.send_pin_reset_otp.assert_not_called()
    sms_sender.send_verification_otp.assert_not_called()
    for row in originals:
        session.refresh(row)
        assert row.attempt_count == 2
        assert row.consumed_at is None
        assert row.code_hash == "private-test-otp-hash"

    allowed = client.post(endpoint, json=payload)
    assert allowed.status_code in {200, 201}, allowed.text
    assert client.post(endpoint, json=payload).status_code == 429
    usage = OtpSupportService(session, settings).usage(flow, subject, now=datetime.now(UTC))
    assert usage.requests_used == 1
    assert usage.next_request_at is not None
    audit = session.scalar(select(AuditLog).where(AuditLog.action == "otp.request_limit_reset"))
    assert audit.admin_user_id == admin.id
    assert audit.details["requests_used_before"] == 3
    assert audit.details["flow"] == flow.value


def test_reset_is_specific_to_one_person_and_flow(otp_support_client):
    client, session, customers, _, settings, *_ = otp_support_client
    for email, flow in [
        ("ama@example.com", OtpFlow.PIN_RESET),
        ("ama@example.com", OtpFlow.USERNAME_RECOVERY),
        ("kwame@example.com", OtpFlow.PIN_RESET),
    ]:
        seed_requests(session, flow, email=email)
    assert reset(client, OtpFlow.PIN_RESET, email_subject(customers[0].email)).status_code == 200
    now = datetime.now(UTC)
    enforce_otp_request_limit(
        session, settings, OtpFlow.PIN_RESET, email_subject(customers[0].email), now=now
    )
    for email, flow in [
        ("ama@example.com", OtpFlow.USERNAME_RECOVERY),
        ("kwame@example.com", OtpFlow.PIN_RESET),
    ]:
        with pytest.raises(ServiceError) as raised:
            enforce_otp_request_limit(session, settings, flow, email_subject(email), now=now)
        assert raised.value.status_code == 429


@pytest.mark.parametrize("role", [AdminRole.VIEWER, AdminRole.OPERATOR])
def test_only_administrator_can_reset(otp_support_client, role):
    client, session, _, admin, *_ = otp_support_client
    admin.role = role
    session.commit()
    assert lookup(client, "ama@example.com")["can_reset"] is False
    assert reset(client, OtpFlow.PIN_RESET, "email:ama@example.com").status_code == 403
    assert session.scalar(select(func.count()).select_from(OtpLimitReset)) == 0


def test_unauthenticated_requests_are_rejected(otp_support_client):
    client, *_ = otp_support_client
    del app.dependency_overrides[get_authenticated_admin]
    assert (
        client.get("/api/admin/otp-support", params={"search": "ama@example.com"}).status_code
        == 401
    )
    assert reset(client, OtpFlow.PIN_RESET, "email:ama@example.com").status_code == 401


def test_reset_persists_in_a_new_database_session(otp_support_client):
    client, session, _, _, settings, *_ = otp_support_client
    seed_requests(session, OtpFlow.REGISTRATION, email="pending@example.com")
    assert reset(client, OtpFlow.REGISTRATION, "email:pending@example.com").status_code == 200
    with Session(session.get_bind()) as restarted:
        enforce_otp_request_limit(
            restarted,
            settings,
            OtpFlow.REGISTRATION,
            "email:pending@example.com",
            now=datetime.now(UTC),
        )
        restored = OtpSupportService(restarted, settings).lookup(
            "pending@example.com", now=datetime.now(UTC)
        )
        assert restored[0].requests_used == 0
        assert restored[0].last_reset_at


def test_reset_history_keeps_administrator_identity_after_email_change(otp_support_client):
    client, session, _, admin, *_ = otp_support_client
    original_email = admin.email
    seed_requests(session, OtpFlow.REGISTRATION, email="pending@example.com")
    assert reset(client, OtpFlow.REGISTRATION, "email:pending@example.com").status_code == 200
    admin.email = "renamed-admin@example.com"
    session.commit()
    assert lookup(client, "pending@example.com")["items"][0]["last_reset_by"] == original_email
    audit = session.scalar(select(AuditLog).where(AuditLog.action == "otp.request_limit_reset"))
    assert audit.details["admin_email"] == original_email


def test_lookup_distinguishes_old_and_current_email_destinations(otp_support_client):
    client, session, customers, *_ = otp_support_client
    customer = customers[0]
    original_email = customer.email
    seed_requests(session, OtpFlow.PIN_RESET, customer=customer)
    customer.email = "new-address@example.com"
    session.commit()
    rows = lookup(client, customer.phone_number)["items"]
    old = next(row for row in rows if row["subject"] == email_subject(original_email))
    current = next(
        row
        for row in rows
        if row["flow"] == "pin_reset" and row["subject"] == email_subject(customer.email)
    )
    assert old["email"] == original_email
    assert old["requests_used"] == 3
    assert current["email"] == customer.email
    assert current["requests_used"] == 0


def test_new_requests_after_reset_still_reach_hourly_limit(otp_support_client):
    client, session, _, _, settings, *_ = otp_support_client
    seed_requests(session, OtpFlow.REGISTRATION, email="pending@example.com")
    assert reset(client, OtpFlow.REGISTRATION, "email:pending@example.com").status_code == 200
    for _ in range(3):
        session.add(
            EmailOtpChallenge(
                email="pending@example.com",
                phone_number="+233241234567",
                purpose=OtpPurpose.REGISTRATION,
                code_hash="hash",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
    session.commit()
    now = datetime.now(UTC) + timedelta(seconds=61)
    with pytest.raises(ServiceError) as raised:
        enforce_otp_request_limit(
            session, settings, OtpFlow.REGISTRATION, "email:pending@example.com", now=now
        )
    assert raised.value.status_code == 429
    assert (
        OtpSupportService(session, settings)
        .usage(OtpFlow.REGISTRATION, "email:pending@example.com", now=now)
        .requests_used
        == 3
    )


@pytest.mark.parametrize("invalid", ["expired", "attempts_exhausted"])
def test_reset_does_not_revive_unusable_codes(otp_support_client, invalid):
    client, session, customers, _, settings, *_ = otp_support_client
    customer = customers[0]
    rows = seed_requests(session, OtpFlow.PIN_RESET, customer=customer)
    row = rows[-1]
    from app.services.pin_management import PinManagementService

    row.code_hash = PinManagementService._hash_code(
        settings.otp_hash_secret.get_secret_value().encode(), row.id, "135790", OtpPurpose.PIN_RESET
    )
    if invalid == "expired":
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    else:
        row.consumed_at = datetime.now(UTC)
    session.commit()
    assert reset(client, OtpFlow.PIN_RESET, email_subject(customer.email)).status_code == 200
    response = client.post(
        "/api/auth/pin-reset/complete",
        json={
            "challenge_id": str(row.id),
            "email": customer.email,
            "code": "135790",
            "new_pin": "654321",
            "new_pin_confirmation": "654321",
        },
    )
    assert response.status_code == 400
    assert customer.pin_hash == "hashed"


def test_retry_time_handles_usage_above_limit(otp_support_client):
    _, session, _, _, settings, *_ = otp_support_client
    now = datetime.now(UTC)
    times = [now - timedelta(minutes=minute) for minute in (50, 40, 30, 20)]
    seed_requests(session, OtpFlow.REGISTRATION, email="pending@example.com", times=times)
    row = OtpSupportService(session, settings).usage(
        OtpFlow.REGISTRATION, "email:pending@example.com", now=now
    )
    assert row.requests_used == 4
    assert row.requests_remaining == 0
    assert row.next_request_at == times[1] + timedelta(hours=1)


@pytest.mark.parametrize(
    "body",
    [
        {"flow": "not_a_flow", "subject": "email:ama@example.com"},
        {"flow": "pin_reset", "subject": "customer:" + str(uuid.uuid4())},
        {"flow": "phone_verification", "subject": "email:ama@example.com"},
        {"flow": "phone_verification", "subject": "customer:invalid"},
        {"flow": "registration", "subject": "email:bad email"},
    ],
)
def test_invalid_reset_targets_are_rejected(otp_support_client, body):
    client, *_ = otp_support_client
    assert client.post("/api/admin/otp-support/reset", json=body).status_code == 422


def test_unknown_subject_has_no_reset_and_lookup_is_empty(otp_support_client):
    client, session, *_ = otp_support_client
    assert lookup(client, "unknown@example.com")["items"] == []
    assert reset(client, OtpFlow.REGISTRATION, "email:unknown@example.com").status_code == 404
    assert session.scalar(select(func.count()).select_from(OtpLimitReset)) == 0


def test_migration_can_upgrade_and_downgrade_without_changing_challenges(support_db):
    session, *_ = support_db
    engine = session.get_bind()
    path = Path(__file__).parents[1] / "alembic/versions/20261017_0016_otp_limit_resets.py"
    spec = importlib.util.spec_from_file_location("otp_reset_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        OtpLimitReset.__table__.drop(connection)
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            assert "otp_limit_resets" in inspect(connection).get_table_names()
            migration.downgrade()
            assert "otp_limit_resets" not in inspect(connection).get_table_names()
            assert "email_otp_challenges" in inspect(connection).get_table_names()
