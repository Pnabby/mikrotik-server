from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register every relationship target
from app.core.config import Settings, get_settings
from app.core.security import Argon2PinHasher
from app.db.base import Base
from app.db.session import get_db_session
from app.integrations.paystack import InitializedTransaction, VerifiedTransaction
from app.main import create_app
from app.models.activation import Activation
from app.models.customer import Customer
from app.models.enums import (
    AccountStatus,
    ActivationStatus,
    PaymentEventStatus,
    PaymentStatus,
    RouterStatus,
    SubscriptionStatus,
)
from app.models.package import Package, RouterPackageProfile
from app.models.payment_event import PaymentEvent
from app.models.router import Router
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.routes.payments import get_payment_router_client_factory, get_paystack_gateway

PAYSTACK_SECRET = "sk_test_payment-integration-secret"


class FakePaystackGateway:
    def __init__(self) -> None:
        self.initializations: list[dict[str, object]] = []
        self.amount_adjustment = 0

    def initialize_transaction(self, **values: object) -> InitializedTransaction:
        self.initializations.append(values)
        reference = str(values["reference"])
        return InitializedTransaction(
            authorization_url=f"https://checkout.paystack.com/{reference}",
            access_code="test-access-code",
            reference=reference,
        )

    def verify_transaction(self, reference: str) -> VerifiedTransaction:
        initialized = next(
            item for item in self.initializations if item["reference"] == reference
        )
        return VerifiedTransaction(
            reference=reference,
            status="success",
            amount=int(initialized["amount"]) + self.amount_adjustment,
            currency=str(initialized["currency"]),
            paid_at=datetime.now(UTC),
            customer_email=str(initialized["email"]),
            metadata=dict(initialized["metadata"]),
        )


class FakeActivationRouter:
    def __init__(self, *, fail_read: bool = False, fail_write: bool = False) -> None:
        self.fail_read = fail_read
        self.fail_write = fail_write
        self.disconnected = False
        self.user = {
            "id": "*1",
            "name": "amab",
            "profile": "disabled",
            "comment": "registered",
            "disabled": "yes",
        }

    def get_hotspot_user(self, username: str) -> dict[str, str] | None:
        if self.fail_read:
            raise OSError("simulated router connection failure")
        return dict(self.user) if username == self.user["name"] else None

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None:
        return {"id": "*P1", "name": profile} if profile == "weekly-20gb" else None

    def activate_hotspot_user(
        self,
        *,
        username: str,
        profile: str,
        comment: str,
        data_limit_bytes: int | None,
    ) -> dict[str, str]:
        if self.fail_write:
            raise OSError("simulated router write failure")
        assert username == self.user["name"]
        self.user.update(
            {
                "profile": profile,
                "comment": comment,
                "disabled": "no",
                "limit-bytes-total": str(data_limit_bytes or 0),
            }
        )
        return dict(self.user)

    def disconnect(self) -> None:
        self.disconnected = True


@pytest.fixture
def payment_settings() -> Settings:
    return Settings(
        _env_file=None,
        pin_hash_secret="a-payment-test-secret-that-is-over-32-characters",
        paystack_secret_key=PAYSTACK_SECRET,
        paystack_public_key="pk_test_payment-integration-public",
        paystack_callback_url="https://tunnel.example/api/payments/paystack/callback",
        frontend_url="http://localhost:5173",
    )


@pytest.fixture
def payment_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def add_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def payment_customer(
    payment_session: Session,
    payment_settings: Settings,
) -> Customer:
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
        pin_hash=Argon2PinHasher.from_settings(payment_settings).hash("483265"),
        account_status=AccountStatus.INACTIVE,
        email_verified_at=now,
        mikrotik_user_verified_at=now,
        last_activity_at=now,
        terms_accepted_at=now,
        terms_version="legacy-test",
        privacy_notice_version="legacy-test",
    )
    package = Package(
        code="weekly",
        name="Weekly Plan",
        amount=Decimal("25.00"),
        currency="GHS",
        duration_seconds=7 * 24 * 60 * 60,
        data_limit_bytes=20 * 1024**3,
        device_limit=2,
    )
    payment_session.add_all(
        [
            customer,
            RouterPackageProfile(
                router=router,
                package=package,
                mikrotik_profile="weekly-20gb",
                display_name="Platinum Week Pass",
            ),
        ]
    )
    payment_session.commit()
    return customer


@pytest.fixture
def payment_app(
    payment_session: Session,
    payment_settings: Settings,
    payment_customer: Customer,
) -> Generator[tuple[TestClient, FakePaystackGateway, FakeActivationRouter], None, None]:
    application = create_app()
    gateway = FakePaystackGateway()
    router_client = FakeActivationRouter()

    def override_session() -> Generator[Session, None, None]:
        yield payment_session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_settings] = lambda: payment_settings
    application.dependency_overrides[get_paystack_gateway] = lambda: gateway
    application.dependency_overrides[get_payment_router_client_factory] = (
        lambda: (lambda _router_id: router_client)
    )
    with TestClient(application) as client:
        assert client.post(
            "/api/auth/login",
            json={"username": payment_customer.username, "pin": "483265"},
        ).status_code == status.HTTP_200_OK
        yield client, gateway, router_client


def _initialize(client: TestClient, customer: Customer, session: Session) -> str:
    package_id = session.scalar(
        select(RouterPackageProfile.package_id).where(
            RouterPackageProfile.router_id == customer.router_id
        )
    )
    response = client.post(
        "/api/payments/initialize",
        json={"package_id": str(package_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["authorization_url"].startswith("https://checkout.paystack.com/")
    return response.json()["reference"]


def test_initialize_records_purchase_before_redirecting_to_paystack(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, gateway, _router_client = payment_app

    reference = _initialize(client, payment_customer, payment_session)

    transaction = payment_session.scalar(
        select(Transaction).where(Transaction.paystack_reference == reference)
    )
    activation = payment_session.scalar(select(Activation))
    assert transaction is not None
    assert transaction.payment_status == PaymentStatus.PENDING
    assert transaction.amount == Decimal("25.00")
    assert activation is not None
    assert activation.transaction_id == transaction.id
    assert activation.target_profile == "weekly-20gb"
    assert gateway.initializations[0]["amount"] == 2500
    assert gateway.initializations[0]["callback_url"] == (
        "https://tunnel.example/api/payments/paystack/callback"
    )


def test_initialize_stops_before_checkout_when_router_is_unreachable(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, gateway, router_client = payment_app
    router_client.fail_read = True
    package_id = payment_session.scalar(
        select(RouterPackageProfile.package_id).where(
            RouterPackageProfile.router_id == payment_customer.router_id
        )
    )

    response = client.post(
        "/api/payments/initialize",
        json={"package_id": str(package_id)},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json() == {
        "detail": "The router service is temporarily unavailable. Please try again later."
    }
    assert gateway.initializations == []
    assert payment_session.scalar(select(Transaction)) is None
    assert payment_session.scalar(select(Activation)) is None


def test_callback_verifies_payment_activates_router_and_starts_subscription(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, _gateway, router_client = payment_app
    reference = _initialize(client, payment_customer, payment_session)

    response = client.get(
        "/api/payments/paystack/callback",
        params={"reference": reference},
        follow_redirects=False,
    )

    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"].startswith(
        "http://localhost:5173/account?payment=active"
    )
    transaction = payment_session.scalar(select(Transaction))
    activation = payment_session.scalar(select(Activation))
    subscription = payment_session.scalar(select(Subscription))
    payment_session.refresh(payment_customer)
    assert transaction is not None and transaction.payment_status == PaymentStatus.SUCCESS
    assert activation is not None and activation.status == ActivationStatus.SUCCESS
    assert subscription is not None and subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.starts_at is None
    assert subscription.expires_at is None
    assert payment_customer.account_status == AccountStatus.ACTIVE
    assert router_client.user["profile"] == "weekly-20gb"
    assert router_client.user["disabled"] == "no"
    assert router_client.user["comment"] == f"activation={activation.activation_id}"


def test_webhook_requires_signature_and_is_idempotent(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, _gateway, _router_client = payment_app
    reference = _initialize(client, payment_customer, payment_session)
    payload = json.dumps(
        {"event": "charge.success", "data": {"reference": reference}},
        separators=(",", ":"),
    ).encode()

    assert client.post(
        "/api/payments/paystack/webhook",
        content=payload,
        headers={"content-type": "application/json", "x-paystack-signature": "invalid"},
    ).status_code == status.HTTP_401_UNAUTHORIZED
    signature = hmac.new(PAYSTACK_SECRET.encode(), payload, hashlib.sha512).hexdigest()
    first = client.post(
        "/api/payments/paystack/webhook",
        content=payload,
        headers={"content-type": "application/json", "x-paystack-signature": signature},
    )
    second = client.post(
        "/api/payments/paystack/webhook",
        content=payload,
        headers={"content-type": "application/json", "x-paystack-signature": signature},
    )

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    events = payment_session.scalars(select(PaymentEvent)).all()
    subscriptions = payment_session.scalars(select(Subscription)).all()
    assert len(events) == 1
    assert events[0].status == PaymentEventStatus.PROCESSED
    assert len(subscriptions) == 1


def test_verification_mismatch_never_activates_access(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, gateway, router_client = payment_app
    reference = _initialize(client, payment_customer, payment_session)
    gateway.amount_adjustment = 1

    response = client.get(
        "/api/payments/paystack/callback",
        params={"reference": reference},
        follow_redirects=False,
    )

    assert "payment=failed" in response.headers["location"]
    transaction = payment_session.scalar(select(Transaction))
    assert transaction is not None and transaction.payment_status == PaymentStatus.PENDING
    assert transaction.failure_code == "payment_verification_mismatch"
    assert payment_session.scalar(select(Subscription)) is None
    assert router_client.user["disabled"] == "yes"


def test_paid_purchase_stays_paid_when_router_write_needs_reconciliation(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, _gateway, router_client = payment_app
    router_client.fail_write = True
    reference = _initialize(client, payment_customer, payment_session)

    response = client.get(
        "/api/payments/paystack/callback",
        params={"reference": reference},
        follow_redirects=False,
    )

    transaction = payment_session.scalar(select(Transaction))
    activation = payment_session.scalar(select(Activation))
    assert "payment=activation_pending" in response.headers["location"]
    assert transaction is not None and transaction.payment_status == PaymentStatus.SUCCESS
    assert activation is not None
    assert activation.status == ActivationStatus.RECONCILIATION_REQUIRED
    assert payment_session.scalar(select(Subscription)) is None

    router_client.fail_write = False
    retry = client.post(f"/api/payments/{reference}/verify")

    assert retry.status_code == status.HTTP_200_OK
    assert retry.json()["activation_status"] == "success"
    assert payment_session.scalar(select(Subscription)) is not None


def test_new_purchase_supersedes_existing_subscription(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, _gateway, _router_client = payment_app
    first_reference = _initialize(client, payment_customer, payment_session)
    assert client.get(
        "/api/payments/paystack/callback",
        params={"reference": first_reference},
        follow_redirects=False,
    ).status_code == status.HTTP_303_SEE_OTHER
    first_subscription = payment_session.scalar(
        select(Subscription).where(
            Subscription.transaction.has(paystack_reference=first_reference)
        )
    )
    assert first_subscription is not None

    second_reference = _initialize(client, payment_customer, payment_session)
    second_response = client.get(
        "/api/payments/paystack/callback",
        params={"reference": second_reference},
        follow_redirects=False,
    )

    payment_session.refresh(first_subscription)
    second_subscription = payment_session.scalar(
        select(Subscription).where(
            Subscription.transaction.has(paystack_reference=second_reference)
        )
    )
    assert second_response.status_code == status.HTTP_303_SEE_OTHER
    assert "payment=active" in second_response.headers["location"]
    assert second_subscription is not None
    assert second_subscription.status == SubscriptionStatus.ACTIVE
    assert first_subscription.status == SubscriptionStatus.SUPERSEDED
    assert first_subscription.superseded_by_id == second_subscription.id


def test_promotional_plan_can_create_only_one_subscription_per_customer(
    payment_app: tuple[TestClient, FakePaystackGateway, FakeActivationRouter],
    payment_session: Session,
    payment_customer: Customer,
) -> None:
    client, _gateway, _router_client = payment_app
    package = payment_session.scalar(select(Package))
    assert package is not None
    package.is_promotional = True
    payment_session.commit()

    # Two checkouts may have been opened before the first one was paid.
    first_reference = _initialize(client, payment_customer, payment_session)
    second_reference = _initialize(client, payment_customer, payment_session)
    first = client.get(
        "/api/payments/paystack/callback",
        params={"reference": first_reference},
        follow_redirects=False,
    )
    second = client.get(
        "/api/payments/paystack/callback",
        params={"reference": second_reference},
        follow_redirects=False,
    )

    assert "payment=active" in first.headers["location"]
    assert "payment=promo_already_used" in second.headers["location"]
    assert len(payment_session.scalars(select(Subscription)).all()) == 1
    second_activation = payment_session.scalar(
        select(Activation).where(
            Activation.transaction.has(paystack_reference=second_reference)
        )
    )
    assert second_activation is not None
    assert second_activation.status == ActivationStatus.SUPERSEDED

    blocked = client.post(
        "/api/payments/initialize",
        json={"package_id": str(package.id)},
    )
    assert blocked.status_code == status.HTTP_409_CONFLICT
