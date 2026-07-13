from fastapi.testclient import TestClient

from mikrotik.api import app, get_client
from mikrotik.pages import (
    STATUS_COOKIE_NAME,
    STATUS_DEVICE_IP_COOKIE_NAME,
    STATUS_DEVICE_MAC_COOKIE_NAME,
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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
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


def test_launch_status_sets_cookie_and_redirects_to_root() -> None:
    client = TestClient(app)
    response = client.post("/launch-status", data={"username": "alice"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert STATUS_COOKIE_NAME in response.headers["set-cookie"]


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

    page_response = client.get("/")
    assert 'const CURRENT_DEVICE_IP = normalizeIpAddress("10.0.0.2")' in page_response.text
    assert (
        'const CURRENT_DEVICE_MAC = normalizeMacAddress("AA:BB:CC:DD:EE:01")'
        in page_response.text
    )
    assert "This device" in page_response.text


def test_launch_status_get_redirects_to_root() -> None:
    response = TestClient(app).get("/launch-status", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


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


def test_status_page_accepts_current_device_identifiers_in_query() -> None:
    response = TestClient(app).get("/?ip=10.0.0.2&mac=aa-bb-cc-dd-ee-01")

    assert 'const CURRENT_DEVICE_IP = normalizeIpAddress("10.0.0.2")' in response.text
    assert 'const CURRENT_DEVICE_MAC = normalizeMacAddress("aa-bb-cc-dd-ee-01")' in response.text


def test_status_page_renders_locked_username_from_cookie() -> None:
    client = TestClient(app)
    client.cookies.set(STATUS_COOKIE_NAME, "alice")

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "alice" in response.text
    assert "Voucher details are locked to your current hotspot session." in response.text


def test_status_page_ignores_query_username_without_locked_cookie() -> None:
    response = TestClient(app).get("/status?username=alice")

    assert response.status_code == 200
    assert "Waiting for hotspot session" in response.text
    assert "Find another voucher" in response.text
    assert 'id="open-lookup-modal"' in response.text
    assert 'id="lookup-modal" hidden' in response.text
    assert 'aria-labelledby="lookup-modal-title"' in response.text
    assert "Check voucher" in response.text
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert 'id="password-toggle"' in response.text
    assert 'aria-label="Show password"' in response.text
    assert 'id="loading-overlay"' in response.text
    assert "Please be patient" in response.text
    assert "Still working on it" in response.text


def test_status_page_path_does_not_unlock_username() -> None:
    response = TestClient(app).get("/status/alice")

    assert response.status_code == 200
    assert "Waiting for hotspot session" in response.text


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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["logged_in_date"] == "2026-05-25 12:05:54"
    assert response.json()["expiry_date"] == "2026-06-25 12:05:54"


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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["expiry_date"] == "2026-02-28 12:05:54"


def test_get_hotspot_status_returns_404_when_user_does_not_exist() -> None:
    fake_client = FakeMikroTikClient(hotspot_user=None)

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/alice/status")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Hotspot user 'alice' was not found."


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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/hotspot/user-lookup",
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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/hotspot/user-lookup",
        json={"username": "alice", "password": "wrong"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."
    assert fake_client.usage_calls == []


def test_lookup_hotspot_user_does_not_reveal_missing_username() -> None:
    fake_client = FakeMikroTikClient(hotspot_user=None)

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/hotspot/user-lookup",
        json={"username": "missing", "password": "anything"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_lookup_hotspot_user_requires_both_credentials() -> None:
    fake_client = FakeMikroTikClient()

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/hotspot/user-lookup",
        json={"username": "alice", "password": ""},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Username and password are required."


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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).get("/api/hotspot/users/ALICE/status")
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

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post("/api/hotspot/users/alice/devices/%2A2/logout")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "username": "alice",
        "session_id": "*2",
        "removed": True,
        "detail": "Device session logged out successfully.",
    }
    assert fake_client.remove_calls == [("alice", "*2", None, None)]


def test_logout_hotspot_device_passes_device_identifiers_to_client() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=True,
    )

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post(
        "/api/hotspot/users/alice/devices/%2A2/logout?mac_address=AA%3ABB&ip_address=10.0.0.2"
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert fake_client.remove_calls == [("alice", "*2", "AA:BB", "10.0.0.2")]


def test_logout_hotspot_device_returns_404_when_session_is_missing() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=False,
    )

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post("/api/hotspot/users/alice/devices/%2A2/logout")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Active session '*2' was not found for user 'alice'."


def test_logout_hotspot_device_uses_canonical_router_username() -> None:
    fake_client = FakeMikroTikClient(
        hotspot_user={"name": "alice", "profile": "weekly-20gb"},
        remove_result=True,
    )

    app.dependency_overrides[get_client] = lambda: fake_client
    response = TestClient(app).post("/api/hotspot/users/ALICE/devices/%2A2/logout")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert fake_client.remove_calls == [("alice", "*2", None, None)]
