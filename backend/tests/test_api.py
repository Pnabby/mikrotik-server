from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.dependencies as dependency_module
from app.dependencies import get_mikrotik_client
from app.main import app
from app.routes.pages import (
    STATUS_COOKIE_NAME,
    STATUS_DEVICE_IP_COOKIE_NAME,
    STATUS_DEVICE_MAC_COOKIE_NAME,
    STATUS_ROUTER_COOKIE_NAME,
)


class FakeMikroTikClient:
    def __init__(
        self,
        *,
        hotspot_user: dict[str, str] | None = None,
        usage: dict[str, int | str | None] | None = None,
        devices: list[dict[str, str]] | None = None,
        remove_result: bool = True,
    ) -> None:
        self.hotspot_user = hotspot_user
        self.usage = usage or {}
        self.devices = devices or []
        self.remove_result = remove_result
        self.remove_calls: list[tuple[str, str]] = []
        self.usage_calls: list[str] = []
        self.device_calls: list[str] = []

    def get_hotspot_user(self, username: str) -> dict[str, str] | None:
        return self.hotspot_user

    def get_hotspot_user_usage(self, username: str) -> dict[str, int | str | None]:
        self.usage_calls.append(username)
        return self.usage

    def get_hotspot_active_devices(self, username: str) -> list[dict[str, str]]:
        self.device_calls.append(username)
        return self.devices

    def remove_hotspot_active_device(
        self,
        username: str,
        session_id: str,
        *,
        mac_address: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        self.remove_calls.append((username, session_id, mac_address, ip_address))
        return self.remove_result


def test_get_hotspot_status_returns_usage_profile_and_devices() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "weekly",
            "comment": "login=2026-05-11 08:15:00",
        },
        usage={
            "combined_bytes_total": 2500,
            "limit_bytes_total": 7000,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
        devices=[
            {
                "id": "*1",
                "device-name": "Alice-iPhone",
                "mac-address": "AA:BB:CC:DD:EE:01",
                "address": "10.0.0.2",
                "bytes-in": "100",
                "bytes-out": "200",
                "bytes-total": "300",
            }
        ],
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "router_id": "flint-main",
        "router_name": "Flint Main",
        "username": "alice",
        "profile": "weekly",
        "disabled": False,
        "logged_in_date": "2026-05-11 08:15:00",
        "expiry_date": "2026-05-18 08:15:00",
        "total_data_used_bytes": 2500,
        "total_data_used": "2.44 KB",
        "total_data_left_bytes": 4500,
        "total_data_left": "4.39 KB",
        "data_limit_bytes": 7000,
        "connected_devices_count": 1,
        "connected_devices": [
            {
                "session_id": "*1",
                "device_name": "Alice-iPhone",
                "device_type": "Phone",
                "mac_address": "AA:BB:CC:DD:EE:01",
                "ip_address": "10.0.0.2",
                "login_by": None,
                "uptime": None,
                "server": None,
                "bytes_in": 100,
                "bytes_out": 200,
                "bytes_total": 300,
            }
        ],
    }


def test_get_hotspot_status_reports_selected_router() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "always-on"},
        usage={
            "combined_bytes_total": 0,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/platinum/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["router_id"] == "platinum"
    assert response.json()["router_name"] == "Platinum"


def test_launch_status_sets_cookie_and_redirects_to_status_page() -> None:
    client = TestClient(app)
    response = client.post("/launch-status", data={"username": "alice"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/status"
    assert STATUS_COOKIE_NAME in response.headers["set-cookie"]
    assert client.cookies.get(STATUS_ROUTER_COOKIE_NAME) == "flint-main"


def test_signup_page_uses_public_spa_route(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(tmp_path / "missing-dist"))
    response = TestClient(app).get("/signup", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/signup"


def test_login_page_uses_public_spa_route(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_DIST_DIR", str(tmp_path / "missing-dist"))
    response = TestClient(app).get("/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/login"


def test_launch_status_keeps_configured_router_id() -> None:
    client = TestClient(app)
    response = client.post(
        "/launch-status",
        data={"username": "alice", "router_id": "platinum"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert client.cookies.get(STATUS_ROUTER_COOKIE_NAME) == "platinum"

    session_response = client.get("/api/status-session")
    assert session_response.json()["selected_router"]["router_id"] == "platinum"
    assert session_response.json()["username"] == "alice"


def test_launch_status_rejects_unconfigured_router_id() -> None:
    response = TestClient(app).post(
        "/launch-status",
        data={"username": "alice", "router_id": "192.0.2.3"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request."


def test_status_session_uses_configured_router_id_from_query() -> None:
    response = TestClient(app).get("/api/status-session?router_id=platinum")

    assert response.status_code == 200
    assert response.json()["selected_router"]["router_id"] == "platinum"
    assert [router["router_id"] for router in response.json()["routers"]] == [
        "flint-main",
        "platinum",
        "flint-annex",
    ]


def test_status_session_rejects_unconfigured_router_id_from_query() -> None:
    response = TestClient(app).get("/api/status-session?router_id=192.0.2.3")

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request."


def test_launch_status_keeps_current_device_identifiers() -> None:
    client = TestClient(app)
    response = client.post(
        "/launch-status",
        data={
            "username": "alice",
            "ip": "10.0.0.2",
            "mac": "AA:BB:CC:DD:EE:01",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert client.cookies.get(STATUS_DEVICE_IP_COOKIE_NAME) == "10.0.0.2"
    assert client.cookies.get(STATUS_DEVICE_MAC_COOKIE_NAME) == "AA:BB:CC:DD:EE:01"

    session_response = client.get("/api/status-session")
    assert session_response.json()["current_device_ip"] == "10.0.0.2"
    assert session_response.json()["current_device_mac"] == "AA:BB:CC:DD:EE:01"


def test_launch_status_get_redirects_to_status_page() -> None:
    response = TestClient(app).get("/launch-status", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/status"


def test_launch_status_get_keeps_mikrotik_device_identifiers() -> None:
    client = TestClient(app)
    response = client.get(
        "/launch-status?username=alice&ip=10.0.0.2&mac=AA%3ABB%3ACC%3ADD%3AEE%3A01",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert client.cookies.get(STATUS_COOKIE_NAME) == "alice"
    assert client.cookies.get(STATUS_DEVICE_IP_COOKIE_NAME) == "10.0.0.2"
    assert client.cookies.get(STATUS_DEVICE_MAC_COOKIE_NAME) == "AA:BB:CC:DD:EE:01"


def test_status_session_accepts_current_device_identifiers_in_query() -> None:
    response = TestClient(app).get(
        "/api/status-session?ip=10.0.0.2&mac=aa-bb-cc-dd-ee-01"
    )

    assert response.json()["current_device_ip"] == "10.0.0.2"
    assert response.json()["current_device_mac"] == "aa-bb-cc-dd-ee-01"


def test_status_session_returns_locked_username_from_cookie() -> None:
    client = TestClient(app)
    client.cookies.set(STATUS_COOKIE_NAME, "alice")

    response = client.get("/api/status-session")

    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_status_session_ignores_query_username_without_locked_cookie() -> None:
    response = TestClient(app).get("/api/status-session?username=alice")

    assert response.status_code == 200
    assert response.json()["username"] is None


def test_list_routers_returns_public_metadata_without_connection_hosts() -> None:
    response = TestClient(app).get("/api/routers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "router_id": "flint-main",
            "name": "Flint Main",
            "hotspot_network": "198.51.100.0/26",
        },
        {
            "router_id": "platinum",
            "name": "Platinum",
            "hotspot_network": "198.51.100.64/26",
        },
        {
            "router_id": "flint-annex",
            "name": "Flint Annex",
            "hotspot_network": "198.51.100.128/26",
        },
    ]
    assert "192.0.2.2" not in response.text
    assert "192.0.2.3" not in response.text
    assert "192.0.2.4" not in response.text


def test_status_api_rejects_raw_host_as_router_id_before_connecting() -> None:
    response = TestClient(app).get(
        "/api/routers/192.0.2.3/hotspot/users/alice/status"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "The requested resource was not found."


def test_get_hotspot_status_returns_unlimited_when_no_limit_exists() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "always-on", "comment": ""},
        usage={
            "combined_bytes_total": 1024,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total_data_left"] == "Unlimited"
    assert response.json()["total_data_left_bytes"] is None
    assert response.json()["logged_in_date"] is None
    assert response.json()["expiry_date"] is None


def test_disabled_hotspot_user_keeps_details_and_reports_disabled_state() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "weekly",
            "disabled": "true",
            "comment": "login=2026-05-11 08:15:00",
        },
        usage={
            "combined_bytes_total": 7000,
            "limit_bytes_total": 7000,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["disabled"] is True
    assert response.json()["profile"] == "weekly"
    assert response.json()["total_data_used_bytes"] == 7000
    assert response.json()["total_data_left_bytes"] == 0


def test_get_hotspot_status_returns_monthly_expiry_from_login_comment() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "monthly",
            "comment": "login=2026-05-25 12:05:54",
        },
        usage={
            "combined_bytes_total": 1024,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["logged_in_date"] == "2026-05-25 12:05:54"
    assert response.json()["expiry_date"] == "2026-06-25 12:05:54"


def test_get_hotspot_status_reads_login_after_activation_marker() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "weekly",
            "comment": "activation=ACT-123;login=2026-05-11 08:15:00",
        },
        usage={
            "combined_bytes_total": 0,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["logged_in_date"] == "2026-05-11 08:15:00"
    assert response.json()["expiry_date"] == "2026-05-18 08:15:00"


def test_activation_marker_does_not_start_login_clock() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "weekly",
            "comment": "activation=ACT-123",
        },
        usage={
            "combined_bytes_total": 0,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["logged_in_date"] is None
    assert response.json()["expiry_date"] is None


def test_get_hotspot_status_clamps_monthly_expiry_to_last_day_of_next_month() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "monthly",
            "comment": "login=2026-01-31 12:05:54",
        },
        usage={
            "combined_bytes_total": 1024,
            "limit_bytes_total": None,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["expiry_date"] == "2026-02-28 12:05:54"


def test_get_hotspot_status_returns_404_when_user_does_not_exist() -> None:
    fake_client = FakeMikroTikClient(hotspot_user=None)

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "The requested resource was not found."


def test_lookup_hotspot_user_returns_status_for_valid_credentials() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "password": "voucher-secret",
            "profile": "weekly",
            "comment": "login=2026-05-11 08:15:00",
        },
        usage={
            "combined_bytes_total": 2500,
            "limit_bytes_total": 7000,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/user-lookup",
        json={"username": " ALICE ", "password": "voucher-secret"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert response.json()["profile"] == "weekly"
    assert fake_client.usage_calls == ["alice"]
    assert fake_client.device_calls == ["alice"]


def test_lookup_hotspot_user_rejects_wrong_password() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "password": "voucher-secret"}
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/user-lookup",
        json={"username": "alice", "password": "wrong"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."
    assert fake_client.usage_calls == []


def test_lookup_hotspot_user_does_not_reveal_missing_username() -> None:
    fake_client = FakeMikroTikClient(hotspot_user=None)

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/user-lookup",
        json={"username": "missing", "password": "anything"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_lookup_hotspot_user_requires_both_credentials() -> None:
    fake_client = FakeMikroTikClient()

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/user-lookup",
        json={"username": "alice", "password": ""},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid request."


def test_get_hotspot_status_uses_canonical_router_username_for_follow_up_queries() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={
            "name": "alice",
            "profile": "weekly",
            "comment": "login=2026-05-11 08:15:00",
        },
        usage={
            "combined_bytes_total": 2500,
            "limit_bytes_total": 7000,
            "limit_bytes_in": None,
            "limit_bytes_out": None,
        },
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).get("/api/routers/flint-main/hotspot/users/ALICE/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert fake_client.usage_calls == ["alice"]
    assert fake_client.device_calls == ["alice"]


def test_logout_hotspot_device_calls_client() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=True,
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/users/alice/devices/%2A2/logout"
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "router_id": "flint-main",
        "router_name": "Flint Main",
        "username": "alice",
        "session_id": "*2",
        "removed": True,
        "detail": "Device session and saved login removed successfully.",
    }
    assert fake_client.remove_calls == [("alice", "*2", None, None)]


def test_logout_hotspot_device_passes_device_identifiers_to_client() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=True,
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/users/alice/devices/%2A2/logout"
        "?mac_address=AA%3ABB&ip_address=10.0.0.2"
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.remove_calls == [("alice", "*2", "AA:BB", "10.0.0.2")]


def test_logout_hotspot_device_returns_404_when_session_is_missing() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=False,
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/users/alice/devices/%2A2/logout"
    )
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "The requested resource was not found."


def test_router_exception_does_not_expose_backend_credentials(
    monkeypatch: MonkeyPatch,
) -> None:
    backend_username = "server-admin"
    backend_password = "backend-password-should-never-leak"

    class LeakyMikroTikClient:
        def __init__(self, _config: object) -> None:
            pass

        def get_hotspot_user(self, _username: str) -> None:
            raise RuntimeError(
                f"executing /login =name={backend_username} =password={backend_password}"
            )

        def disconnect(self) -> None:
            pass

    monkeypatch.setenv("MIKROTIK_USERNAME", backend_username)
    monkeypatch.setenv("MIKROTIK_PASSWORD", backend_password)
    monkeypatch.setattr(dependency_module, "MikroTikClient", LeakyMikroTikClient)

    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/routers/flint-main/hotspot/users/alice/status"
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The router service is temporarily unavailable. Please try again later."
    }
    assert backend_username not in response.text
    assert backend_password not in response.text
    assert "/login" not in response.text


def test_validation_error_does_not_echo_rejected_password() -> None:
    rejected_password = "rejected-password-should-never-leak"

    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/user-lookup",
        json={"username": "alice", "password": {"value": rejected_password}},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
    assert rejected_password not in response.text


def test_logout_hotspot_device_uses_canonical_router_username() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=True,
    )

    app.dependency_overrides[get_mikrotik_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/routers/flint-main/hotspot/users/ALICE/devices/%2A2/logout"
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert fake_client.remove_calls == [("alice", "*2", None, None)]
