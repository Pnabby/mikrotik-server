from app.main import app
from app.services.admin_dashboard import active_identity_sets


def test_dashboard_route_is_registered() -> None:
    assert "/api/admin/dashboard" in app.openapi()["paths"]


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
