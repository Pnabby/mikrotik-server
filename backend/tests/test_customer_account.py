from __future__ import annotations

import hashlib
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all relationship targets with SQLAlchemy
from app.core.config import Settings, get_settings
from app.core.security import Argon2PinHasher
from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.models.customer import Customer
from app.models.customer_session import CustomerSession
from app.models.enums import AccountStatus, PaymentStatus, RouterStatus, SubscriptionStatus
from app.models.package import Package, RouterPackageProfile
from app.models.router import Router
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.routes.account import get_customer_hotspot_service
from app.schemas.hotspot import DeviceLogoutResponse, HotspotStatusResponse
from app.services.customer_auth import CUSTOMER_SESSION_COOKIE


@pytest.fixture
def account_settings() -> Settings:
    return Settings(
        _env_file=None,
        pin_hash_secret="a-customer-login-test-secret-over-32-characters",
        customer_session_ttl_seconds=60 * 60,
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

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def customer(db_session: Session, account_settings: Settings) -> Customer:
    now = datetime.now(UTC)
    router = Router(
        id="platinum",
        name="Platinum Hostel",
        vpn_host="192.0.2.3",
        api_port=8728,
        hotspot_network="198.51.100.64/26",
        status=RouterStatus.ONLINE,
    )
    customer = Customer(
        router=router,
        email="ama@example.com",
        username="amab",
        pin_hash=Argon2PinHasher.from_settings(account_settings).hash("483265"),
        account_status=AccountStatus.INACTIVE,
        email_verified_at=now,
        mikrotik_user_verified_at=now,
    )
    db_session.add(customer)
    db_session.commit()
    return customer


@pytest.fixture
def client(db_session: Session, account_settings: Settings) -> Generator[TestClient, None, None]:
    application = create_app()

    def override_session() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_settings] = lambda: account_settings
    with TestClient(application) as test_client:
        yield test_client


def test_login_creates_hashed_session_and_opens_account(
    client: TestClient,
    db_session: Session,
    customer: Customer,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": " AMAB ", "pin": "483265"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"username": "amab", "redirect_to": "/account"}
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]

    raw_token = client.cookies.get(CUSTOMER_SESSION_COOKIE)
    stored_session = db_session.scalar(select(CustomerSession))
    assert raw_token is not None
    assert stored_session is not None
    assert stored_session.customer_id == customer.id
    assert stored_session.token_hash != raw_token
    assert stored_session.token_hash == hashlib.sha256(
        f"customer-session:{raw_token}".encode()
    ).hexdigest()

    account_response = client.get("/api/account")
    assert account_response.status_code == status.HTTP_200_OK
    assert account_response.json() == {
        "username": "amab",
        "email": "ama@example.com",
        "hostel_name": "Platinum Hostel",
        "account_status": "inactive",
        "current_plan": None,
        "available_plans": [],
        "previous_plans": [],
        "purchases": [],
    }


def test_login_rejects_wrong_pin_without_creating_session(
    client: TestClient,
    db_session: Session,
    customer: Customer,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "111111"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert db_session.scalar(select(CustomerSession)) is None


def test_account_requires_login_and_logout_revokes_session(
    client: TestClient,
    db_session: Session,
    customer: Customer,
) -> None:
    assert client.get("/api/account").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "483265"},
    ).status_code == status.HTTP_200_OK

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == status.HTTP_200_OK
    stored_session = db_session.scalar(select(CustomerSession))
    assert stored_session is not None
    assert stored_session.revoked_at is not None
    assert client.get("/api/account").status_code == status.HTTP_401_UNAUTHORIZED


def test_account_lists_hostel_plans_and_purchase_history(
    client: TestClient,
    db_session: Session,
    customer: Customer,
) -> None:
    package = Package(
        code="weekly",
        name="Weekly Plan",
        description="Seven days of access",
        amount=Decimal("25.00"),
        currency="GHS",
        duration_seconds=7 * 24 * 60 * 60,
        data_limit_bytes=20 * 1024**3,
        device_limit=2,
    )
    db_session.add_all(
        [
            package,
            RouterPackageProfile(
                router_id=customer.router_id,
                package=package,
                mikrotik_profile="weekly-20gb",
                display_name="Platinum Week Pass",
                description="A hostel-specific weekly plan",
                download_speed="10 Mbps",
            ),
        ]
    )
    db_session.flush()
    db_session.add(
        Transaction(
            customer_id=customer.id,
            package_id=package.id,
            router_id=customer.router_id,
            paystack_reference="purchase-test-001",
            amount=package.amount,
            currency=package.currency,
            payment_status=PaymentStatus.SUCCESS,
            paid_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    assert client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "483265"},
    ).status_code == status.HTTP_200_OK

    response = client.get("/api/account")

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["available_plans"] == [
        {
            "id": str(package.id),
            "name": "Platinum Week Pass",
            "description": "A hostel-specific weekly plan",
            "amount": "25.00",
            "currency": "GHS",
            "duration_seconds": 604800,
            "data_limit_bytes": 20 * 1024**3,
            "device_limit": 2,
            "download_speed": "10 Mbps",
            "purchase_available": False,
        }
    ]
    assert payload["purchases"][0]["reference"] == "purchase-test-001"
    assert payload["purchases"][0]["plan_name"] == "Platinum Week Pass"
    assert "mikrotik_profile" not in response.text


def test_account_lists_only_five_most_recent_previous_plans(
    client: TestClient,
    db_session: Session,
    customer: Customer,
) -> None:
    now = datetime.now(UTC)
    subscriptions = []
    for index in range(6):
        package = Package(
            code=f"previous-{index + 1}",
            name=f"Previous plan {index + 1}",
            amount=Decimal("10.00"),
            currency="GHS",
            duration_seconds=86400,
        )
        subscriptions.append(
            Subscription(
                customer_id=customer.id,
                package=package,
                transaction_id=uuid.uuid4(),
                activation_id=uuid.uuid4(),
                router_id=customer.router_id,
                status=SubscriptionStatus.EXPIRED,
                starts_at=now - timedelta(days=index + 1),
                expires_at=now - timedelta(hours=12 * (index + 1)),
                ended_at=now - timedelta(hours=12 * (index + 1)),
            )
        )
    db_session.add_all(subscriptions)
    db_session.commit()
    assert client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "483265"},
    ).status_code == status.HTTP_200_OK

    response = client.get("/api/account")

    assert response.status_code == status.HTTP_200_OK
    previous_plans = response.json()["previous_plans"]
    assert len(previous_plans) == 5
    assert [plan["name"] for plan in previous_plans] == [
        "Previous plan 1",
        "Previous plan 2",
        "Previous plan 3",
        "Previous plan 4",
        "Previous plan 5",
    ]
    assert all(plan["status"] == "expired" for plan in previous_plans)


class RecordingCustomerHotspotService:
    def __init__(self) -> None:
        self.status_usernames: list[str] = []
        self.logout_calls: list[tuple[str, str]] = []

    def get_status(self, username: str) -> HotspotStatusResponse:
        self.status_usernames.append(username)
        return HotspotStatusResponse(
            router_id="platinum",
            router_name="Platinum Hostel",
            username=username,
            profile="weekly",
            disabled=False,
            logged_in_date="2026-09-03 10:00:00",
            expiry_date="2026-09-10 10:00:00",
            total_data_used_bytes=1024,
            total_data_used="1.00 KB",
            total_data_left_bytes=2048,
            total_data_left="2.00 KB",
            data_limit_bytes=3072,
            connected_devices_count=0,
            connected_devices=[],
        )

    def logout_device(
        self,
        username: str,
        session_id: str,
        *,
        mac_address: str | None = None,
        ip_address: str | None = None,
    ) -> DeviceLogoutResponse:
        self.logout_calls.append((username, session_id))
        return DeviceLogoutResponse(
            router_id="platinum",
            router_name="Platinum Hostel",
            username=username,
            session_id=session_id,
            removed=True,
            detail="Device session logged out successfully.",
        )


def test_authenticated_hotspot_status_is_locked_to_logged_in_customer(
    client: TestClient,
    customer: Customer,
) -> None:
    hotspot_service = RecordingCustomerHotspotService()
    client.app.dependency_overrides[get_customer_hotspot_service] = lambda: hotspot_service
    assert client.get("/api/account/hotspot-status").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "483265"},
    ).status_code == status.HTTP_200_OK

    response = client.get("/api/account/hotspot-status", params={"username": "someoneelse"})

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["username"] == customer.username
    assert hotspot_service.status_usernames == [customer.username]


def test_authenticated_device_logout_uses_logged_in_customer(
    client: TestClient,
    customer: Customer,
) -> None:
    hotspot_service = RecordingCustomerHotspotService()
    client.app.dependency_overrides[get_customer_hotspot_service] = lambda: hotspot_service
    assert client.post(
        "/api/auth/login",
        json={"username": customer.username, "pin": "483265"},
    ).status_code == status.HTTP_200_OK

    response = client.post("/api/account/devices/session-1/logout")

    assert response.status_code == status.HTTP_200_OK
    assert hotspot_service.logout_calls == [(customer.username, "session-1")]
