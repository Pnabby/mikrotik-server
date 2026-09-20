from contextlib import contextmanager

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
    assert "/api/admin/dashboard/customers" in paths
    assert "/api/admin/dashboard/access-points" in paths
    assert "/api/payments/claim-free" in paths
    assert "/api/payments/claim-free/{reference}/retry" in paths


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
        hotspot_network="192.168.88.0/23",
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
