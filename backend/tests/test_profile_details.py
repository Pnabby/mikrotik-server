from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import get_db_session
from app.dependencies import get_mikrotik_client
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.enums import AdminRole, RouterStatus
from app.models.package import Package, PlanGroup, RouterPackageProfile
from app.models.transaction import Transaction
from app.routes.admin_auth import get_authenticated_admin


def add_plan(session, router, **overrides):
    package = Package(
        code=f"{router.id}-weekly", name="Weekly", description="Original description",
        amount=10, currency="GHS", duration_seconds=604800, data_limit_bytes=1024**3,
        device_limit=2, is_promotional=False, is_active=True,
    )
    for key, value in overrides.items():
        setattr(package, key, value)
    group = PlanGroup(router_id=router.id, name="Weekly bundles")
    mapping = RouterPackageProfile(
        router=router, package=package, group=group, mikrotik_profile="paid",
        display_name=package.name, description=package.description, download_speed="10 Mbps",
    )
    session.add(mapping)
    session.commit()
    return mapping


@pytest.fixture
def details_client(support_db, monkeypatch):
    session, customers, admin, source, destination = support_db
    mapping = add_plan(session, source)
    source.status = RouterStatus.OFFLINE
    source.last_seen_at = datetime(2026, 10, 1, tzinfo=UTC)
    session.commit()
    calls = []

    def unexpected_router_connection(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("A database-only edit attempted a router connection.")

    monkeypatch.setattr("app.integrations.mikrotik.client.MikroTikClient.__init__",
                        unexpected_router_connection)
    monkeypatch.setattr("app.main.get_settings",
                        lambda: Settings(api_cors_origins="http://localhost:5174"))
    application = create_app()
    application.dependency_overrides[get_db_session] = lambda: session
    application.dependency_overrides[get_authenticated_admin] = lambda: admin
    application.dependency_overrides[get_mikrotik_client] = unexpected_router_connection
    yield TestClient(application), session, admin, source, destination, mapping, customers
    assert calls == []


def test_price_edit_saves_offline_without_router_reads_or_status_changes(details_client):
    client, session, _, source, _, mapping, _ = details_client
    last_seen = source.last_seen_at
    group_id = mapping.group_id
    response = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": "25.75"})

    assert response.status_code == 200, response.text
    saved = response.json()
    assert Decimal(saved["amount"]) == Decimal("25.75")
    assert saved["display_name"] == "Weekly"
    assert saved["duration_seconds"] == 604800
    assert saved["device_limit"] == 2
    assert saved["download_speed"] == "10 Mbps"
    assert saved["is_visible"] is True
    assert "available_on_router" not in saved and "rate_limit" not in saved
    assert mapping.package.amount == Decimal("25.75")
    assert mapping.group_id == group_id
    assert source.status == RouterStatus.OFFLINE and source.last_seen_at == last_seen
    audit = session.scalar(select(AuditLog))
    assert set(audit.details["after"]) == {"amount"}
    assert Decimal(audit.details["after"]["amount"]) == Decimal("25.75")


def test_price_edit_across_hostels_preserves_each_hostels_other_terms(details_client):
    client, session, _, _, destination, mapping, _ = details_client
    other = add_plan(session, destination, name="Annex Weekly", amount=15,
                     description="Annex offer", device_limit=4, duration_seconds=86400,
                     is_active=False, is_promotional=True)
    original_group = other.group_id

    for router_id in ("main", "annex"):
        result = client.patch(f"/api/admin/hostels/{router_id}/profiles/paid",
                              json={"amount": "20.00"})
        assert result.status_code == 200, result.text

    assert mapping.package.amount == other.package.amount == Decimal("20.00")
    assert mapping.display_name == "Weekly" and other.display_name == "Annex Weekly"
    assert mapping.package.duration_seconds == 604800 and other.package.duration_seconds == 86400
    assert mapping.package.device_limit == 2 and other.package.device_limit == 4
    assert other.description == "Annex offer" and other.package.is_promotional is True
    assert other.package.is_active is False and other.group_id == original_group


def test_nullable_fields_can_be_cleared_without_changing_other_terms(details_client):
    client, _, _, _, _, mapping, _ = details_client
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={
        "description": None, "duration_seconds": None, "device_limit": None, "group_id": None,
    })
    assert result.status_code == 200, result.text
    assert mapping.description is None and mapping.package.description is None
    assert mapping.package.duration_seconds is None and mapping.package.device_limit is None
    assert mapping.group_id is None and mapping.package.amount == Decimal("10.00")


@pytest.mark.parametrize("changes", [
    {"amount": None}, {"display_name": None}, {"is_visible": None}, {"amount": -1},
    {"router_settings": {"rate_limit": "5M/10M"}}, {"source_router_id": "main"},
])
def test_invalid_or_router_fields_are_rejected_on_database_only_path(details_client, changes):
    client, _, _, _, _, mapping, _ = details_client
    result = client.patch("/api/admin/hostels/main/profiles/paid", json=changes)
    assert result.status_code == 422
    assert mapping.package.amount == Decimal("10.00")


def test_partial_edits_validate_free_plan_rules_against_saved_terms(details_client):
    client, session, _, _, _, mapping, _ = details_client
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": 0})
    assert result.status_code == 422
    assert result.json()["field_errors"]["plan"] == "A published free plan must be promotional."
    assert mapping.package.amount == Decimal("10.00")

    mapping.package.is_promotional = True
    session.commit()
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": 0})
    assert result.status_code == 200, result.text
    assert mapping.package.is_promotional is True
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"is_promotional": False})
    assert result.status_code == 422
    assert mapping.package.is_promotional is True


def test_group_must_belong_to_selected_hostel(details_client):
    client, session, _, _, destination, mapping, _ = details_client
    group = PlanGroup(router_id=destination.id, name="Annex plans")
    session.add(group)
    session.commit()
    original_group_id = mapping.group_id
    result = client.patch("/api/admin/hostels/main/profiles/paid",
                          json={"group_id": str(group.id), "amount": 20})
    assert result.status_code == 400
    assert mapping.group_id == original_group_id and mapping.package.amount == Decimal("10.00")


def test_unconfigured_plan_requires_original_configuration_path(details_client):
    client, _, _, _, _, _, _ = details_client
    result = client.patch("/api/admin/hostels/main/profiles/missing", json={"amount": 20})
    assert result.status_code == 404


def test_registration_profile_cannot_be_published(details_client):
    client, session, _, _, _, mapping, _ = details_client
    name = Settings().mikrotik_registration_profile
    mapping.mikrotik_profile = name
    mapping.is_active = False
    session.commit()
    result = client.patch(f"/api/admin/hostels/main/profiles/{name}", json={"is_visible": True})
    assert result.status_code == 400
    assert mapping.is_active is False


def test_shared_package_edit_preserves_other_hostel_and_purchase_history(details_client):
    client, session, _, _, destination, mapping, customers = details_client
    original_package = mapping.package
    other = RouterPackageProfile(router=destination, package=original_package, mikrotik_profile="paid")
    session.add(other)
    transaction = Transaction(
        customer_id=customers[0].id, package_id=original_package.id, router_id="main",
        paystack_reference="original-purchase", amount=10,
    )
    session.add_all([other, transaction])
    session.commit()

    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": 20})
    assert result.status_code == 200, result.text
    assert mapping.package_id != original_package.id
    assert mapping.package.amount == Decimal("20.00")
    assert other.package_id == transaction.package_id == original_package.id
    assert original_package.amount == transaction.amount == Decimal("10.00")


def test_unchanged_price_does_not_create_an_audit_or_clone_shared_package(details_client):
    client, session, _, _, destination, mapping, _ = details_client
    original_id = mapping.package_id
    session.add(RouterPackageProfile(router=destination, package=mapping.package, mikrotik_profile="paid"))
    session.commit()
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": "10.00"})
    assert result.status_code == 200
    assert mapping.package_id == original_id
    assert session.scalar(select(AuditLog)) is None


@pytest.mark.parametrize("role,expected", [(AdminRole.VIEWER, 403), (AdminRole.OPERATOR, 200)])
def test_database_only_edit_requires_editor_role(details_client, role, expected):
    client, _, admin, _, _, mapping, _ = details_client
    admin.role = role
    result = client.patch("/api/admin/hostels/main/profiles/paid", json={"amount": 20})
    assert result.status_code == expected
    assert mapping.package.amount == Decimal("20.00" if expected == 200 else "10.00")


def test_browser_can_send_patch_from_admin_origin(details_client):
    client, *_ = details_client
    result = client.options("/api/admin/hostels/main/profiles/paid", headers={
        "Origin": "http://localhost:5174", "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type",
    })
    assert result.status_code == 200, result.text
    assert "PATCH" in result.headers["access-control-allow-methods"]
