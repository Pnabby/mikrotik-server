from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register relationship targets
from app.core.config import Settings, get_settings
from app.core.security import Argon2PasswordHasher
from app.db.base import Base
from app.db.session import get_db_session
from app.dependencies import get_mikrotik_client
from app.main import create_app
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.enums import AdminRole, RouterStatus
from app.models.package import Package, RouterPackageProfile
from app.models.router import Router

ADMIN_PASSWORD = "TestAdminProfiles9!"


class FakeProfileClient:
    def __init__(self) -> None:
        self.profiles = [
            {
                "name": "weekly-20gb",
                "rate-limit": "512k/10M",
                "shared-users": "2",
                "session-timeout": "7d",
                "idle-timeout": "5m",
                "address-pool": "hotspot-pool",
            },
            {"name": "disabled", "shared-users": "1"},
        ]

    def get_hotspot_user_profiles(self) -> list[dict[str, str]]:
        return self.profiles


@pytest.fixture
def admin_profile_session() -> Generator[Session, None, None]:
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
        session.add_all(
            [
                AdminUser(
                    email="admin",
                    password_hash=Argon2PasswordHasher().hash(ADMIN_PASSWORD),
                    role=AdminRole.ADMINISTRATOR,
                ),
                Router(
                    id="platinum",
                    name="Platinum Hostel",
                    location="North campus",
                    vpn_host="192.0.2.3",
                    api_port=8728,
                    hotspot_network="198.51.100.64/26",
                    status=RouterStatus.UNKNOWN,
                ),
            ]
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def profile_client(admin_profile_session: Session) -> Generator[TestClient, None, None]:
    application = create_app()
    router_client = FakeProfileClient()
    settings = Settings(_env_file=None, admin_session_ttl_seconds=3600)

    def override_session() -> Generator[Session, None, None]:
        yield admin_profile_session

    application.dependency_overrides[get_db_session] = override_session
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_mikrotik_client] = lambda: router_client
    with TestClient(application) as test_client:
        yield test_client


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/admin/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200


def test_admin_hostel_catalog_requires_authentication(profile_client: TestClient) -> None:
    assert profile_client.get("/api/admin/hostels").status_code == 401


def test_admin_profile_save_allows_cross_origin_put(profile_client: TestClient) -> None:
    response = profile_client.options(
        "/api/admin/hostels/platinum/profiles/weekly-20gb",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_admin_lists_hostels_and_live_router_profiles(profile_client: TestClient) -> None:
    _login(profile_client)

    hostels_response = profile_client.get("/api/admin/hostels")
    profiles_response = profile_client.get("/api/admin/hostels/platinum/profiles")

    assert hostels_response.status_code == 200
    assert hostels_response.json()[0] == {
        "router_id": "platinum",
        "name": "Platinum Hostel",
        "location": "North campus",
        "vpn_host": "192.0.2.3",
        "api_port": 8728,
        "hotspot_network": "198.51.100.64/26",
        "display_order": 0,
        "status": "unknown",
        "is_active": True,
        "last_seen_at": None,
        "configured_profiles": 0,
        "published_profiles": 0,
    }
    assert profiles_response.status_code == 200
    profiles = profiles_response.json()
    assert [profile["mikrotik_profile"] for profile in profiles] == [
        "weekly-20gb",
        "disabled",
    ]
    assert profiles[0]["rate_limit"] == "512k/10M"
    assert profiles[0]["download_speed"] == "10 Mbps"
    assert profiles[0]["shared_users"] == 2
    assert profiles[0]["is_configured"] is False
    assert profiles[1]["is_registration_profile"] is True


def test_admin_updates_hostel_database_details_and_audits_change(
    profile_client: TestClient,
    admin_profile_session: Session,
) -> None:
    _login(profile_client)

    response = profile_client.put(
        "/api/admin/hostels/platinum",
        json={
            "name": "Platinum Hall",
            "location": "West campus",
            "vpn_host": "192.0.2.44",
            "api_port": 8729,
            "hotspot_network": "198.51.100.128/26",
            "display_order": 4,
            "is_active": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Platinum Hall"
    assert response.json()["vpn_host"] == "192.0.2.44"
    router = admin_profile_session.get(Router, "platinum")
    assert router is not None
    assert router.location == "West campus"
    assert router.api_port == 8729
    assert router.is_active is False
    audit_log = admin_profile_session.scalar(
        select(AuditLog).where(AuditLog.action == "router.updated")
    )
    assert audit_log is not None
    assert audit_log.details is not None
    assert audit_log.details["before"]["name"] == "Platinum Hostel"
    assert audit_log.details["after"]["name"] == "Platinum Hall"

    response = profile_client.put(
        "/api/admin/hostels/platinum",
        json={**response.json(), "is_active": True},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is True


def test_admin_adds_a_hostel_to_the_database_catalogue(
    profile_client: TestClient,
    admin_profile_session: Session,
) -> None:
    _login(profile_client)

    response = profile_client.post(
        "/api/admin/hostels",
        json={
            "router_id": "gold-hostel",
            "name": "Gold Hostel",
            "location": "South campus",
            "vpn_host": "192.0.2.55",
            "api_port": 8728,
            "hotspot_network": "203.0.113.0/25",
            "display_order": 2,
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["router_id"] == "gold-hostel"
    assert response.json()["configured_profiles"] == 0
    created = admin_profile_session.get(Router, "gold-hostel")
    assert created is not None
    assert created.name == "Gold Hostel"
    audit_log = admin_profile_session.scalar(
        select(AuditLog).where(AuditLog.action == "router.created")
    )
    assert audit_log is not None
    assert audit_log.entity_id == "gold-hostel"

    duplicate = profile_client.post(
        "/api/admin/hostels",
        json={
            "router_id": "another-hostel",
            "name": "Another Hostel",
            "vpn_host": "192.0.2.55",
            "api_port": 8728,
            "hotspot_network": "203.0.113.128/25",
            "display_order": 3,
            "is_active": True,
        },
    )
    assert duplicate.status_code == 409


def test_admin_configures_customer_facing_profile_and_audits_change(
    profile_client: TestClient,
    admin_profile_session: Session,
) -> None:
    _login(profile_client)

    response = profile_client.put(
        "/api/admin/hostels/platinum/profiles/weekly-20gb",
        json={
            "display_name": "Campus Weekly Plus",
            "description": "Fast WiFi for a full week.",
            "amount": "25.00",
            "currency": "GHS",
            "duration_seconds": 604800,
            "data_limit_bytes": 21474836480,
            "device_limit": 2,
            "download_speed": "15 Mbps",
            "is_promotional": True,
            "is_visible": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "Campus Weekly Plus"
    assert payload["amount"] == "25.00"
    assert payload["is_visible"] is True
    assert payload["download_speed"] == "15 Mbps"
    assert payload["is_promotional"] is True
    mapping = admin_profile_session.scalar(select(RouterPackageProfile))
    package = admin_profile_session.scalar(select(Package))
    audit_log = admin_profile_session.scalar(select(AuditLog))
    assert mapping is not None and mapping.display_name == "Campus Weekly Plus"
    assert mapping is not None and mapping.download_speed == "15 Mbps"
    assert package is not None and package.name == "Campus Weekly Plus"
    assert package.is_promotional is True
    assert package.code == "platinum-weekly-20gb"
    assert audit_log is not None
    assert audit_log.action == "router_profile.configured"
    assert audit_log.details is not None
    assert audit_log.details["mikrotik_profile"] == "weekly-20gb"
    assert audit_log.details["download_speed"] == "15 Mbps"

    no_duration_response = profile_client.put(
        "/api/admin/hostels/platinum/profiles/weekly-20gb",
        json={
            "display_name": "Campus Weekly Plus",
            "amount": "25.00",
            "currency": "GHS",
            "duration_seconds": None,
            "download_speed": "20 Mbps",
            "is_promotional": True,
            "is_visible": True,
        },
    )
    assert no_duration_response.status_code == 200
    assert no_duration_response.json()["duration_seconds"] is None
    assert package.duration_seconds is None
    assert mapping.download_speed == "20 Mbps"

    hostels = profile_client.get("/api/admin/hostels").json()
    assert hostels[0]["configured_profiles"] == 1
    assert hostels[0]["published_profiles"] == 1


def test_registration_profile_cannot_be_published(profile_client: TestClient) -> None:
    _login(profile_client)

    response = profile_client.put(
        "/api/admin/hostels/platinum/profiles/disabled",
        json={
            "display_name": "Disabled",
            "amount": "0.00",
            "currency": "GHS",
            "duration_seconds": 86400,
            "is_visible": True,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request."}


def test_configured_profile_missing_from_router_remains_visible_to_admin(
    profile_client: TestClient,
    admin_profile_session: Session,
) -> None:
    package = Package(
        code="retired-plan",
        name="Retired plan",
        amount=Decimal("15.00"),
        currency="GHS",
        duration_seconds=86400,
        is_active=False,
    )
    admin_profile_session.add(
        RouterPackageProfile(
            router_id="platinum",
            package=package,
            mikrotik_profile="removed-from-router",
            display_name="Old day pass",
            is_active=False,
        )
    )
    admin_profile_session.commit()
    _login(profile_client)

    response = profile_client.get("/api/admin/hostels/platinum/profiles")

    assert response.status_code == 200
    missing = next(
        item for item in response.json() if item["mikrotik_profile"] == "removed-from-router"
    )
    assert missing["display_name"] == "Old day pass"
    assert missing["available_on_router"] is False
    assert missing["is_visible"] is False


def test_viewer_cannot_change_profile_configuration(
    profile_client: TestClient,
    admin_profile_session: Session,
) -> None:
    _login(profile_client)
    admin = admin_profile_session.scalar(select(AdminUser))
    assert admin is not None
    admin.role = AdminRole.VIEWER
    admin_profile_session.commit()

    response = profile_client.put(
        "/api/admin/hostels/platinum/profiles/weekly-20gb",
        json={
            "display_name": "Weekly pass",
            "amount": "25.00",
            "currency": "GHS",
            "duration_seconds": 604800,
            "is_visible": True,
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}

    create_response = profile_client.post(
        "/api/admin/hostels",
        json={
            "router_id": "viewer-hostel",
            "name": "Viewer Hostel",
            "vpn_host": "192.0.2.99",
            "api_port": 8728,
            "hotspot_network": "203.0.113.0/25",
            "display_order": 5,
            "is_active": True,
        },
    )
    assert create_response.status_code == 403
