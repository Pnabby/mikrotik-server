from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all relationship targets with SQLAlchemy
import app.services.registration as registration_service_module
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.db.base import Base
from app.db.session import get_db_session
from app.integrations.brevo.client import EmailDeliveryError
from app.main import create_app
from app.models.customer import Customer
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import AccountStatus
from app.models.router import Router
from app.routes.registration import (
    get_otp_email_sender,
    get_pin_hasher,
    get_registration_router_client_factory,
)
from app.schemas.registration import RegistrationCompleteRequest, RegistrationStartRequest
from app.services.registration import RegistrationAvailabilityService, RegistrationOtpService


class RecordingEmailSender:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_registration_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        self.messages.append(
            {
                "recipient": recipient,
                "code": code,
                "expires_in_minutes": expires_in_minutes,
            }
        )


class FailingEmailSender:
    def send_registration_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("provider unavailable")


class RecordingPinHasher:
    def __init__(self, events: list[str] | None = None) -> None:
        self.events = events

    def hash(self, pin: str) -> str:
        if self.events is not None:
            self.events.append("pin-hash")
        return "$argon2id$test-pin-hash"


class FakeRegistrationRouterClient:
    def __init__(
        self,
        *,
        events: list[str] | None = None,
        has_disabled_profile: bool = True,
        fail_create: bool = False,
        unavailable: bool = False,
    ) -> None:
        self.events = events
        self.fail_create = fail_create
        self.unavailable = unavailable
        self.profiles = {"disabled": {"name": "disabled"}} if has_disabled_profile else {}
        self.users: dict[str, dict[str, str]] = {}
        self.disconnected = False

    def get_hotspot_user(self, username: str) -> dict[str, str] | None:
        if self.unavailable:
            raise RuntimeError("router unavailable")
        return self.users.get(username)

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None:
        if self.unavailable:
            raise RuntimeError("router unavailable")
        return self.profiles.get(profile)

    def create_hotspot_user(
        self,
        *,
        username: str,
        password: str,
        profile: str,
        comment: str,
        disabled: bool = True,
    ) -> None:
        if self.events is not None:
            self.events.append("router-create")
        if self.fail_create:
            raise RuntimeError("router unavailable")
        self.users[username] = {
            "id": "*1",
            "name": username,
            "password": password,
            "profile": profile,
            "comment": comment,
            "disabled": "true" if disabled else "false",
        }

    def remove_hotspot_user(self, username: str, *, expected_comment: str) -> bool:
        user = self.users.get(username)
        if user is None:
            return True
        if user.get("comment") != expected_comment:
            return False
        del self.users[username]
        if self.events is not None:
            self.events.append("router-remove")
        return True

    def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def otp_settings() -> Settings:
    return Settings(
        _env_file=None,
        otp_hash_secret="a-secure-test-secret-that-is-over-32-characters",
        pin_hash_secret="a-different-pin-secret-that-is-over-32-characters",
        otp_code_ttl_seconds=600,
        otp_resend_cooldown_seconds=60,
        otp_max_attempts=3,
        otp_max_requests_per_hour=5,
        mikrotik_registration_profile="disabled",
    )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def add_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    registration_tables = [
        Router.__table__,
        Customer.__table__,
        EmailOtpChallenge.__table__,
    ]
    Base.metadata.create_all(engine, tables=registration_tables)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            Router(
                id="platinum",
                name="Platinum Hostel",
                vpn_host="192.0.2.3",
                api_port=8728,
                hotspot_network="198.51.100.64/26",
                is_active=True,
            )
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine, tables=reversed(registration_tables))
    engine.dispose()


def registration_payload() -> RegistrationStartRequest:
    return RegistrationStartRequest(
        email="ama@example.com",
        username="amab",
        router_id="platinum",
        pin="483265",
        accepted_terms=True,
    )


def completion_payload(challenge_id: object, code: str) -> RegistrationCompleteRequest:
    return RegistrationCompleteRequest(
        challenge_id=challenge_id,
        code=code,
        email="ama@example.com",
        username="amab",
        router_id="platinum",
        pin="483265",
        accepted_terms=True,
    )


def start_otp(
    db_session: Session,
    otp_settings: Settings,
    sender: RecordingEmailSender,
) -> tuple[object, str]:
    started = RegistrationOtpService(db_session, sender, otp_settings).start(
        registration_payload(),
        FakeRegistrationRouterClient(),
        requested_ip="192.0.2.10",
    )
    return started, str(sender.messages[-1]["code"])


def test_username_suggestions_skip_random_candidates_already_in_database(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    router = db_session.get(Router, "platinum")
    assert router is not None
    db_session.add_all(
        [
            Customer(
                router=router,
                email="ama@example.com",
                username="amab",
                pin_hash="$argon2id$existing",
                account_status=AccountStatus.INACTIVE,
                email_verified_at=now,
                mikrotik_user_verified_at=now,
                last_activity_at=now,
                terms_accepted_at=now,
                terms_version="legacy-test",
                privacy_notice_version="legacy-test",
            ),
            Customer(
                router=router,
                email="taken@example.com",
                username="amab1000",
                pin_hash="$argon2id$existing",
                account_status=AccountStatus.INACTIVE,
                email_verified_at=now,
                mikrotik_user_verified_at=now,
                last_activity_at=now,
                terms_accepted_at=now,
                terms_version="legacy-test",
                privacy_notice_version="legacy-test",
            ),
        ]
    )
    db_session.commit()

    suffixes = iter(range(32))
    monkeypatch.setattr(
        registration_service_module.secrets,
        "randbelow",
        lambda _upper_bound: next(suffixes),
    )

    result = RegistrationAvailabilityService(db_session).check_username("amab")

    assert result.available is False
    assert result.suggestions == ["amab1001", "amab1002", "amab1003"]


def test_registration_creates_verified_disabled_router_user_before_database_customer(
    db_session: Session, otp_settings: Settings
) -> None:
    events: list[str] = []
    sender = RecordingEmailSender()
    started, code = start_otp(db_session, otp_settings, sender)
    router_client = FakeRegistrationRouterClient(events=events)

    @event.listens_for(db_session, "before_flush")
    def record_customer_write(session: Session, _flush_context: object, _instances: object) -> None:
        if any(isinstance(item, Customer) for item in session.new):
            events.append("database-customer")

    completed = RegistrationOtpService(db_session, sender, otp_settings).complete(
        completion_payload(started.challenge_id, code),
        router_client,
        RecordingPinHasher(events),
    )

    assert events == ["router-create", "pin-hash", "database-customer"]
    assert completed.username == "amab"
    assert completed.account_status == AccountStatus.INACTIVE
    assert completed.router_user_disabled is True
    assert router_client.users["amab"] == {
        "id": "*1",
        "name": "amab",
        "password": "483265",
        "profile": "disabled",
        "comment": f"flint-registration={started.challenge_id}",
        "disabled": "true",
    }

    customer = db_session.get(Customer, completed.customer_id)
    assert customer is not None
    assert customer.email == "ama@example.com"
    assert customer.username == "amab"
    assert customer.router_id == "platinum"
    assert customer.pin_hash == "$argon2id$test-pin-hash"
    assert "483265" not in customer.pin_hash
    assert customer.email_verified_at is not None
    assert customer.mikrotik_user_verified_at is not None
    assert customer.account_status == AccountStatus.INACTIVE

    database_router = db_session.get(Router, "platinum")
    assert database_router is not None
    assert database_router.vpn_host == "192.0.2.3"
    challenge = db_session.get(EmailOtpChallenge, started.challenge_id)
    assert challenge is not None
    assert challenge.customer_id == customer.id
    assert challenge.verified_at is not None
    assert challenge.consumed_at is not None


def test_registration_otp_is_hashed_before_completion(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    started, sent_code = start_otp(db_session, otp_settings, sender)
    challenge = db_session.get(EmailOtpChallenge, started.challenge_id)

    assert started.destination == "a**@example.com"
    assert challenge is not None
    assert sent_code not in challenge.code_hash
    assert challenge.code_hash.startswith("hmac-sha256$")
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


def test_completed_registration_is_idempotent(
    db_session: Session, otp_settings: Settings
) -> None:
    events: list[str] = []
    sender = RecordingEmailSender()
    started, code = start_otp(db_session, otp_settings, sender)
    request = completion_payload(started.challenge_id, code)
    router_client = FakeRegistrationRouterClient(events=events)
    service = RegistrationOtpService(db_session, sender, otp_settings)

    first = service.complete(request, router_client, RecordingPinHasher())
    second = service.complete(request, router_client, RecordingPinHasher())

    assert second.customer_id == first.customer_id
    assert events.count("router-create") == 1
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_invalid_codes_are_limited(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    started, sent_code = start_otp(db_session, otp_settings, sender)
    wrong_code = "000000" if sent_code != "000000" else "000001"
    request = completion_payload(started.challenge_id, wrong_code)
    service = RegistrationOtpService(db_session, sender, otp_settings)

    for expected_status in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_429_TOO_MANY_REQUESTS,
    ):
        with pytest.raises(ServiceError) as error:
            service.complete(request, FakeRegistrationRouterClient(), RecordingPinHasher())
        assert error.value.status_code == expected_status

    challenge = db_session.get(EmailOtpChallenge, started.challenge_id)
    assert challenge is not None
    assert challenge.attempt_count == 3
    assert challenge.consumed_at is not None


def test_registration_requires_disabled_router_profile(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    started, code = start_otp(db_session, otp_settings, sender)
    router_client = FakeRegistrationRouterClient(has_disabled_profile=False)

    with pytest.raises(ServiceError) as error:
        RegistrationOtpService(db_session, sender, otp_settings).complete(
            completion_payload(started.challenge_id, code),
            router_client,
            RecordingPinHasher(),
        )

    assert error.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert router_client.users == {}
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


def test_router_creation_failure_does_not_create_database_customer(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    started, code = start_otp(db_session, otp_settings, sender)
    router_client = FakeRegistrationRouterClient(fail_create=True)

    with pytest.raises(ServiceError) as error:
        RegistrationOtpService(db_session, sender, otp_settings).complete(
            completion_payload(started.challenge_id, code),
            router_client,
            RecordingPinHasher(),
        )

    assert error.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


def test_database_failure_removes_newly_created_router_user(
    db_session: Session, otp_settings: Settings
) -> None:
    events: list[str] = []
    sender = RecordingEmailSender()
    started, code = start_otp(db_session, otp_settings, sender)
    router_client = FakeRegistrationRouterClient(events=events)

    def fail_customer_commit(session: Session) -> None:
        if any(isinstance(item, Customer) for item in session.new):
            raise SQLAlchemyError("simulated database outage")

    event.listen(db_session, "before_commit", fail_customer_commit)
    try:
        with pytest.raises(ServiceError) as error:
            RegistrationOtpService(db_session, sender, otp_settings).complete(
                completion_payload(started.challenge_id, code),
                router_client,
                RecordingPinHasher(events),
            )
    finally:
        event.remove(db_session, "before_commit", fail_customer_commit)

    assert error.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert events[-1] == "router-remove"
    assert router_client.users == {}
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 0


def test_registration_otp_resend_has_a_cooldown(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    service = RegistrationOtpService(db_session, sender, otp_settings)
    router_client = FakeRegistrationRouterClient()
    service.start(
        registration_payload(),
        router_client,
        requested_ip="192.0.2.10",
    )

    with pytest.raises(ServiceError) as error:
        service.start(
            registration_payload(),
            router_client,
            requested_ip="192.0.2.10",
        )

    assert error.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert len(sender.messages) == 1


def test_failed_delivery_invalidates_challenge(
    db_session: Session, otp_settings: Settings
) -> None:
    service = RegistrationOtpService(db_session, FailingEmailSender(), otp_settings)

    with pytest.raises(ServiceError) as error:
        service.start(
            registration_payload(),
            FakeRegistrationRouterClient(),
            requested_ip="192.0.2.10",
        )

    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    challenge = db_session.scalar(select(EmailOtpChallenge))
    assert challenge is not None
    assert challenge.consumed_at is not None


def test_unavailable_router_prevents_otp_email_and_challenge(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    router_client = FakeRegistrationRouterClient(unavailable=True)
    application = create_app()

    def override_session() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_settings] = lambda: otp_settings
    application.dependency_overrides[get_otp_email_sender] = lambda: sender
    application.dependency_overrides[get_registration_router_client_factory] = (
        lambda: lambda _router_id: router_client
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/registration/start",
            json={
                "email": "ama@example.com",
                "username": "amab",
                "router_id": "platinum",
                "pin": "483265",
                "accepted_terms": True,
            },
        )

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert response.json()["detail"] == (
        "The router service is temporarily unavailable. Please try again later."
    )
    assert sender.messages == []
    assert db_session.scalar(select(func.count()).select_from(EmailOtpChallenge)) == 0
    assert router_client.disconnected is True


def test_router_readiness_rejects_username_already_on_selected_hostel(
    otp_settings: Settings,
) -> None:
    router_client = FakeRegistrationRouterClient()
    router_client.users["amab"] = {"id": "*1", "name": "amab"}
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: otp_settings
    application.dependency_overrides[get_registration_router_client_factory] = (
        lambda: lambda _router_id: router_client
    )

    with TestClient(application) as client:
        response = client.get(
            "/api/registration/router-readiness",
            params={"router_id": "platinum", "username": "amab"},
        )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert router_client.disconnected is True


def test_registration_endpoints_create_router_and_database_users(
    db_session: Session, otp_settings: Settings
) -> None:
    sender = RecordingEmailSender()
    router_client = FakeRegistrationRouterClient()
    application = create_app()

    def override_session() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_settings] = lambda: otp_settings
    application.dependency_overrides[get_otp_email_sender] = lambda: sender
    application.dependency_overrides[get_pin_hasher] = lambda: RecordingPinHasher()
    application.dependency_overrides[get_registration_router_client_factory] = (
        lambda: lambda _router_id: router_client
    )

    with TestClient(application) as client:
        available = client.get(
            "/api/registration/username-availability",
            params={"username": " AMAB "},
        )
        assert available.status_code == status.HTTP_200_OK
        assert available.json() == {
            "username": "amab",
            "available": True,
            "suggestions": [],
        }

        readiness = client.get(
            "/api/registration/router-readiness",
            params={"router_id": "platinum", "username": "amab"},
        )
        assert readiness.status_code == status.HTTP_200_OK
        assert readiness.json() == {
            "router_id": "platinum",
            "username": "amab",
            "ready": True,
        }

        started = client.post(
            "/api/registration/start",
            json={
                "email": "ama@example.com",
                "username": "amab",
                "router_id": "platinum",
                "pin": "483265",
                "accepted_terms": True,
            },
        )
        assert started.status_code == status.HTTP_201_CREATED
        start_response = started.json()
        assert start_response["destination"] == "a**@example.com"
        assert "code" not in start_response

        completed = client.post(
            "/api/registration/complete",
            json={
                "challenge_id": start_response["challenge_id"],
                "email": "ama@example.com",
                "username": "amab",
                "router_id": "platinum",
                "pin": "483265",
                "accepted_terms": True,
                "code": sender.messages[0]["code"],
            },
        )

        unavailable = client.get(
            "/api/registration/username-availability",
            params={"username": "amab"},
        )

    assert completed.status_code == status.HTTP_200_OK
    assert completed.json()["username"] == "amab"
    assert completed.json()["account_status"] == "inactive"
    assert completed.json()["router_user_disabled"] is True
    assert router_client.users["amab"]["profile"] == "disabled"
    assert router_client.users["amab"]["disabled"] == "true"
    assert router_client.disconnected is True
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    assert unavailable.status_code == status.HTTP_200_OK
    unavailable_body = unavailable.json()
    assert unavailable_body["username"] == "amab"
    assert unavailable_body["available"] is False
    suggestions = unavailable_body["suggestions"]
    assert len(suggestions) == 3
    assert len(set(suggestions)) == 3
    assert all(
        suggestion.startswith("amab")
        and suggestion[len("amab") :].isdigit()
        and len(suggestion[len("amab") :]) == 4
        for suggestion in suggestions
    )
