from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.main import app
from app.models.router import Router
from app.services.admin_dashboard import (
    AdminDashboardService,
    active_identity_sets,
    enabled_hotspot_usernames,
)


def test_dashboard_route_is_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/admin/dashboard" in paths
    assert "/api/admin/dashboard/transactions" in paths
    assert "/api/admin/dashboard/analytics" in paths
    assert "/api/admin/dashboard/customers" in paths
    assert "/api/admin/dashboard/access-points" in paths
    assert "/api/admin/dashboard/network-usage" in paths
    assert "/api/payments/claim-free" in paths
    assert "/api/payments/claim-free/{reference}/retry" in paths


def test_admin_spa_deep_link_and_assets_are_served(tmp_path, monkeypatch) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (tmp_path / "index.html").write_text("admin-spa", encoding="utf-8")
    (assets / "app.js").write_text("admin-asset", encoding="utf-8")
    settings = get_settings().model_copy(update={"admin_dist_dir": tmp_path})
    monkeypatch.setattr("app.routes.pages.get_settings", lambda: settings)
    client = TestClient(app)

    deep_link = client.get("/admin/analysis", follow_redirects=False)
    asset = client.get("/admin/assets/app.js", follow_redirects=False)

    assert deep_link.status_code == 200
    assert deep_link.text == "admin-spa"
    assert asset.status_code == 200
    assert asset.text == "admin-asset"


def test_active_identity_sets_deduplicates_users_and_devices() -> None:
    sessions = [
        {"user": "Alice", "mac-address": "AA:AA:AA:AA:AA:AA"},
        {"user": " alice ", "mac-address": "AA:AA:AA:AA:AA:AA"},
        {"user": "bob", "mac-address": "BB:BB:BB:BB:BB:BB"},
        {"user": "", "mac-address": "CC:CC:CC:CC:CC:CC"},
    ]

    users, devices = active_identity_sets("hostel-one", sessions)

    assert users == {"alice", "bob"}
    assert len(devices) == 2


def test_device_identity_is_scoped_to_router() -> None:
    session = [{"user": "alice", "mac-address": "AA:AA:AA:AA:AA:AA"}]

    _, first_router_devices = active_identity_sets("hostel-one", session)
    _, second_router_devices = active_identity_sets("hostel-two", session)

    assert len(first_router_devices | second_router_devices) == 2


def test_enabled_hotspot_usernames_excludes_disabled_and_deduplicates() -> None:
    users = [
        {"name": "Alice", "disabled": "false"},
        {"name": " alice ", "disabled": "no"},
        {"name": "bob", "disabled": "true"},
        {"name": "carol", "disabled": "yes"},
        {"name": "david", "disabled": "0"},
        {"name": "", "disabled": "false"},
    ]

    assert enabled_hotspot_usernames(users) == {"alice", "david"}


def test_live_router_status_counts_enabled_hotspot_users(monkeypatch) -> None:
    class FakeClient:
        def get_hotspot_active_sessions(self):
            return [{"user": "alice", "mac-address": "AA:AA:AA:AA:AA:AA"}]

        def get_hotspot_users(self):
            return [
                {"name": "alice", "disabled": "false"},
                {"name": "bob", "disabled": "true"},
                {"name": "carol", "disabled": "no"},
            ]

    @contextmanager
    def fake_context(_definition):
        yield FakeClient()

    monkeypatch.setattr("app.services.admin_dashboard.mikrotik_client_context", fake_context)
    hostel = Router(
        id="hall", name="Hall", vpn_host="hall.example", api_port=8728,
        hotspot_network="192.168.88.0/23", is_active=True,
    )

    status, usernames, devices = AdminDashboardService(None)._live_router_status(hostel)

    assert status.reachable is True
    assert status.active_subscriptions == 2
    assert usernames == {"alice"}
    assert len(devices) == 1


def test_network_usage_maps_ether1_live_and_total_traffic(monkeypatch) -> None:
    class FakeClient:
        def get_interface_traffic(self, interface_name):
            assert interface_name == "ether1"
            return {
                "name": "ether1",
                "type": "ether",
                "running": True,
                "disabled": False,
                "download_bps": 8_000_000,
                "upload_bps": 2_000_000,
                "download_bytes": 12_000_000_000,
                "upload_bytes": 3_000_000_000,
            }

    @contextmanager
    def fake_context(_definition):
        yield FakeClient()

    monkeypatch.setattr("app.services.admin_dashboard.mikrotik_client_context", fake_context)
    hostel = Router(
        id="hall", name="Hall", vpn_host="hall.example", api_port=8728,
        hotspot_network="192.168.88.0/23", is_active=True,
    )

    result = AdminDashboardService(None).network_usage(hostel)

    assert result.router_reachable is True
    assert result.interface_running is True
    assert result.download_bps == 8_000_000
    assert result.upload_bps == 2_000_000
    assert result.total_usage_bytes == 15_000_000_000


def test_mikrotik_client_reads_interface_counters_and_live_rates(monkeypatch) -> None:
    class FakeInterfaceResource:
        def get(self, **filters):
            assert filters == {"name": "ether1"}
            return [{
                "name": "ether1",
                "type": "ether",
                "running": "true",
                "disabled": "false",
                "rx-byte": "12000",
                "tx-byte": "3000",
            }]

        def call(self, command, arguments):
            assert command == "monitor-traffic"
            assert arguments == {"interface": "ether1", "once": ""}
            return [{
                "rx-bits-per-second": "8000000",
                "tx-bits-per-second": "2000000",
            }]

    class FakeApi:
        def get_resource(self, path):
            assert path == "/interface"
            return FakeInterfaceResource()

    client = MikroTikClient(MikroTikConfig(host="router", username="admin", password="secret"))
    monkeypatch.setattr(client, "connect", lambda: FakeApi())

    traffic = client.get_interface_traffic("ether1")

    assert traffic["running"] is True
    assert traffic["download_bps"] == 8_000_000
    assert traffic["upload_bps"] == 2_000_000
    assert traffic["download_bytes"] == 12_000
    assert traffic["upload_bytes"] == 3_000


def test_access_points_only_include_leases_in_range_and_use_active_mac(monkeypatch) -> None:
    class FakeClient:
        def get_dhcp_leases(self):
            return [
                {
                    "address": "192.168.88.2",
                    "mac-address": "AA:AA:AA:AA:AA:AA",
                    "active-mac-address": "AA:AA:AA:AA:AA:AA",
                    "host-name": "hall-ap-2",
                    "comment": "Second-floor corridor",
                },
                {
                    "address": "192.168.88.3",
                    "mac-address": "BB:BB:BB:BB:BB:BB",
                },
                {
                    "address": "192.168.88.50",
                    "mac-address": "CC:CC:CC:CC:CC:CC",
                    "active-mac-address": "CC:CC:CC:CC:CC:CC",
                },
            ]

        def get_bridge_hosts(self):
            return [{"mac-address": "AA:AA:AA:AA:AA:AA", "on-interface": "ether3"}]

    @contextmanager
    def fake_context(_definition):
        yield FakeClient()

    monkeypatch.setattr("app.services.admin_dashboard.mikrotik_client_context", fake_context)
    hostel = Router(
        id="hall", name="Hall", vpn_host="hall.example", api_port=8728,
        hotspot_network="192.168.88.0/23", is_active=True,
    )

    result = AdminDashboardService(None).access_points(hostel)

    assert len(result.access_points) == 2
    assert result.access_points[0].ip_address == "192.168.88.2"
    assert result.access_points[-1].ip_address == "192.168.88.3"
    assert result.access_points[0].online is True
    assert result.access_points[0].connected_port == "ether3"
    assert result.access_points[0].comment == "Second-floor corridor"
    assert result.access_points[1].online is False
    assert result.online_count == 1
    assert result.offline_count == 1


def test_customer_allowance_includes_live_usage_and_router_identity():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from app.models.enums import AccountStatus, SubscriptionStatus

    now = datetime(2026, 10, 1, 18, 56, 27, tzinfo=UTC)
    package = SimpleNamespace(name="Weekly", data_limit_bytes=1000, duration_seconds=604800)
    subscription = SimpleNamespace(created_at=now, status=SubscriptionStatus.ACTIVE,
                                   package=package, expires_at=now + timedelta(days=2))
    customer = SimpleNamespace(id="customer", username="alice", email="a@example.com",
                               phone_number=None, phone_verified_at=None, router_id="one",
                               router=SimpleNamespace(name="Hostel"),
                               account_status=AccountStatus.ACTIVE, subscriptions=[subscription],
                               created_at=now, last_login_at=None, last_activity_at=now)
    users = {"one": [{"name": "alice", "limit-bytes-total": "1000",
                      "bytes-in": "500", "bytes-out": "200",
                      "comment": "login=2026-09-26 18:56:27;activation=ACT-TEST"}]}
    devices = [("one", "session", "alice", {"bytes-in": "50", "bytes-out": "100"})]
    detail = AdminDashboardService._customer_detail(
        customer, {"alice"}, {("one", "alice"): 1}, users, devices, now=now)
    assert detail.data_remaining_bytes == 150
    assert detail.router_online is True
    assert detail.is_online is True
    assert 172790 <= detail.remaining_seconds <= 172800

    offline = AdminDashboardService._customer_detail(customer, {"alice"}, {}, {}, [])
    assert offline.router_online is False
    assert offline.is_online is False
    assert offline.data_remaining_bytes is None


def test_customer_edit_normalizes_contact_and_resets_verification():
    import uuid
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from app.models.enums import AdminRole
    from app.routes.admin_dashboard import update_customer
    from app.schemas.admin_dashboard import AdminCustomerUpdateRequest

    now = datetime.now(UTC)
    customer = SimpleNamespace(id=uuid.uuid4(), email="old@example.com",
                               phone_number="+233241234567", email_verified_at=now,
                               phone_verified_at=now)
    admin = SimpleNamespace(id=uuid.uuid4(), role=AdminRole.OPERATOR)

    class Session:
        def __init__(self):
            self.audit = []
            self.committed = False
        def scalar(self, query):
            return customer
        def add(self, row):
            self.audit.append(row)
        def commit(self):
            self.committed = True

    session = Session()
    update_customer(customer.id,
                    AdminCustomerUpdateRequest(email=" NEW@EXAMPLE.COM ", phone_number="024 765 4321"),
                    SimpleNamespace(client=None), admin, session)
    assert customer.email == "new@example.com"
    assert customer.phone_number == "+233247654321"
    assert customer.email_verified_at is None
    assert customer.phone_verified_at is None
    assert session.committed
    assert session.audit[0].details == {"fields": ["email", "phone_number"]}


def test_customer_edit_rejects_viewer_and_duplicate_contact():
    import uuid
    import pytest
    from types import SimpleNamespace
    from sqlalchemy.exc import IntegrityError
    from app.core.exceptions import ServiceError
    from app.models.enums import AdminRole
    from app.routes.admin_dashboard import update_customer
    from app.schemas.admin_dashboard import AdminCustomerUpdateRequest

    customer = SimpleNamespace(id=uuid.uuid4(), email="old@example.com",
                               phone_number=None, email_verified_at=None, phone_verified_at=None)
    payload = AdminCustomerUpdateRequest(email="new@example.com")

    class Session:
        rolled_back = False
        def scalar(self, query):
            return customer
        def add(self, row):
            pass
        def commit(self):
            raise IntegrityError("update", {}, Exception("duplicate"))
        def rollback(self):
            self.rolled_back = True

    session = Session()
    with pytest.raises(ServiceError) as forbidden:
        update_customer(customer.id, payload, SimpleNamespace(client=None),
                        SimpleNamespace(id=uuid.uuid4(), role=AdminRole.VIEWER), session)
    assert forbidden.value.status_code == 403
    with pytest.raises(ServiceError) as conflict:
        update_customer(customer.id, payload, SimpleNamespace(client=None),
                        SimpleNamespace(id=uuid.uuid4(), role=AdminRole.OPERATOR), session)
    assert conflict.value.status_code == 409
    assert session.rolled_back


def _allowance_customer(now, *, duration=604800, data_limit=1000):
    from types import SimpleNamespace
    from app.models.enums import AccountStatus, SubscriptionStatus
    package = SimpleNamespace(name="Weekly", data_limit_bytes=data_limit, duration_seconds=duration)
    subscription = SimpleNamespace(created_at=now, status=SubscriptionStatus.ACTIVE,
                                   package=package, expires_at=None)
    return SimpleNamespace(id="customer", username="alice", email="a@example.com",
                           phone_number=None, phone_verified_at=None, router_id="one",
                           router=SimpleNamespace(name="Hostel"), account_status=AccountStatus.INACTIVE,
                           subscriptions=[subscription], created_at=now, last_login_at=None,
                           last_activity_at=now)


def test_time_allowance_uses_router_comment_and_configured_profile():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from app.models.enums import AccountStatus
    now = datetime(2026, 10, 1, 6, 56, 27, tzinfo=UTC)
    customer = _allowance_customer(now, duration=86400)
    user = {"name": "alice", "profile": "weekly-standard", "disabled": "no",
            "comment": "login=2026-09-28 18:56:27;activation=ACT-3515E9C20F964F9BB72EF96ED18A21A4"}
    mapping = SimpleNamespace(display_name="7 days Standard",
                              package=SimpleNamespace(name="Weekly", duration_seconds=604800,
                                                      data_limit_bytes=None))
    detail = AdminDashboardService._customer_detail(
        customer, set(), {}, {"one": [user]}, [],
        {("one", "weekly-standard"): mapping}, now)
    assert detail.remaining_seconds == 4 * 86400 + 12 * 3600
    assert detail.expires_at == datetime(2026, 10, 5, 18, 56, 27, tzinfo=UTC)
    assert detail.current_plan == "7 days Standard"
    assert detail.account_status == AccountStatus.ACTIVE  # Web account is inactive.
    assert detail.time_usage_unavailable_reason is None

    expired = AdminDashboardService._customer_detail(
        customer, set(), {}, {"one": [dict(user, disabled="yes")]}, [],
        {("one", "weekly-standard"): mapping}, now + timedelta(days=8))
    assert expired.account_status == AccountStatus.INACTIVE
    assert expired.remaining_seconds == 0


def test_missing_time_comment_and_offline_router_have_explanations():
    from datetime import UTC, datetime
    now = datetime(2026, 10, 1, tzinfo=UTC)
    customer = _allowance_customer(now)
    for comment in ("activation=ACT-TEST", "login=invalid;activation=ACT-TEST"):
        detail = AdminDashboardService._customer_detail(
            customer, set(), {}, {"one": [{"name": "alice", "comment": comment}]}, [], now=now)
        assert detail.remaining_seconds is None
        assert detail.time_usage_unavailable_reason == "Router comment has no valid login timestamp."
    offline = AdminDashboardService._customer_detail(customer, set(), {}, {}, [], now=now)
    assert offline.account_status is None
    assert offline.remaining_seconds is None
    assert offline.time_usage_unavailable_reason == "Router offline; login timestamp cannot be read."


def test_data_left_subtracts_saved_and_all_active_device_counters():
    from datetime import UTC, datetime
    now = datetime(2026, 10, 1, tzinfo=UTC)
    customer = _allowance_customer(now, duration=None)
    user = {"name": "alice", "disabled": "true", "limit-bytes-total": "1000",
            "bytes-in": "500", "bytes-out": "100"}
    rows = [("one", "first", "alice", {"bytes-in": "100", "bytes-out": "50"}),
            ("one", "second", "ALICE", {"bytes-in": "30", "bytes-out": "20"}),
            ("other-hostel", "third", "alice", {"bytes-in": "10000"}),
            ("one", "fourth", "bob", {"bytes-in": "10000"})]
    detail = AdminDashboardService._customer_detail(customer, set(), {}, {"one": [user]}, rows)
    assert detail.data_remaining_bytes == 200  # 80% used; 20% remaining.
    exhausted = AdminDashboardService._customer_detail(
        customer, set(), {}, {"one": [dict(user, **{"bytes-in": "2000"})]}, rows)
    assert exhausted.data_remaining_bytes == 0


def test_customer_directory_sort_orders_all_rows_before_paging():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    now = datetime.now(UTC)
    customers = [
        SimpleNamespace(id="1", username="zoe", current_plan="Basic", last_activity_at=now),
        SimpleNamespace(id="2", username="Alice", current_plan=None, last_activity_at=now - timedelta(days=1)),
        SimpleNamespace(id="3", username="bob", current_plan="Premium", last_activity_at=now - timedelta(days=2)),
        SimpleNamespace(id="4", username="amy", current_plan="basic", last_activity_at=now),
    ]
    sort = AdminDashboardService._sort_customer_directory
    assert [row.username for row in sort(customers, "username", "asc")] == ["Alice", "amy", "bob", "zoe"]
    assert [row.username for row in sort(customers, "current_plan", "asc")] == ["amy", "zoe", "bob", "Alice"]
    assert [row.username for row in sort(customers, "current_plan", "desc")] == ["bob", "amy", "zoe", "Alice"]
    assert [row.username for row in sort(customers, "last_activity_at", "desc")[1:3]] == ["zoe", "Alice"]
    assert [row.username for row in sort(customers, "last_activity_at", "asc")] == ["bob", "Alice", "amy", "zoe"]
