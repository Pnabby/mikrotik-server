from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig, infer_device_type


class FakeResource:
    def __init__(self, records: list[dict[str, str]]) -> None:
        self.records = records
        self.removed_ids: list[str] = []

    def get(self, **filters: str) -> list[dict[str, str]]:
        if not filters:
            return self.records

        return [
            record
            for record in self.records
            if all(record.get(key) == value for key, value in filters.items())
        ]

    def remove(self, **filters: str) -> None:
        session_id = filters.get("id")
        if session_id is None:
            raise AssertionError("Expected id filter when removing hotspot session")

        self.removed_ids.append(session_id)
        self.records[:] = [record for record in self.records if record.get("id") != session_id]


class FakeApi:
    def __init__(
        self,
        sessions: list[dict[str, str]],
        users: list[dict[str, str]] | None = None,
        leases: list[dict[str, str]] | None = None,
    ) -> None:
        self.active_resource = FakeResource(sessions)
        self.user_resource = FakeResource(users or [])
        self.lease_resource = FakeResource(leases or [])

    def get_resource(self, path: str) -> FakeResource:
        if path == "/ip/hotspot/active":
            return self.active_resource
        if path == "/ip/hotspot/user":
            return self.user_resource
        if path == "/ip/dhcp-server/lease":
            return self.lease_resource
        raise AssertionError(f"Unexpected path: {path}")


def test_get_hotspot_active_device_count_counts_matching_sessions() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {"user": "alice", "address": "10.0.0.2"},
            {"user": "alice", "address": "10.0.0.3"},
            {"user": "bob", "address": "10.0.0.4"},
        ]
    )

    assert client.get_hotspot_active_device_count("alice") == 2


def test_get_hotspot_active_devices_returns_matching_sessions() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "address": "10.0.0.2",
                "mac-address": "AA:BB:CC:DD:EE:01",
                "host-name": "Hotspot-Fallback",
            },
            {
                "id": "*2",
                "user": "alice",
                "address": "10.0.0.3",
                "mac-address": "AA:BB:CC:DD:EE:02",
            },
            {
                "id": "*3",
                "user": "bob",
                "address": "10.0.0.4",
                "mac-address": "AA:BB:CC:DD:EE:03",
            },
        ],
        users=[
            {
                "name": "alice",
                "comment": "Parent account",
                "bytes-in": "500",
                "bytes-out": "1000",
                "limit-bytes-total": "5000",
            }
        ],
        leases=[
            {
                "mac-address": "aa-bb-cc-dd-ee-01",
                "host-name": "Alice-iPhone",
            },
            {
                "mac-address": "AA:BB:CC:DD:EE:03",
                "host-name": "Bobs-Phone",
            },
        ],
    )

    devices = client.get_hotspot_active_devices("alice")

    assert devices == [
        {
            "id": "*1",
            "user": "alice",
            "address": "10.0.0.2",
            "mac-address": "AA:BB:CC:DD:EE:01",
            "host-name": "Hotspot-Fallback",
            "bytes-in": "0",
            "bytes-out": "0",
            "bytes-total": "0",
            "device-name": "Alice-iPhone",
            "device-type": "Phone",
            "user-comment": "Parent account",
        },
        {
            "id": "*2",
            "user": "alice",
            "address": "10.0.0.3",
            "mac-address": "AA:BB:CC:DD:EE:02",
            "bytes-in": "0",
            "bytes-out": "0",
            "bytes-total": "0",
            "device-name": "unknown",
            "device-type": "Unknown",
            "user-comment": "Parent account",
        },
    ]


def test_get_hotspot_active_devices_falls_back_when_dhcp_hostname_is_empty() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:01",
                "host": "Active-Session-Name",
            },
        ],
        leases=[
            {
                "mac-address": "AA:BB:CC:DD:EE:01",
                "host-name": "  ",
            },
        ],
    )

    devices = client.get_hotspot_active_devices("alice")

    assert devices[0]["device-name"] == "Active-Session-Name"


def test_get_hotspot_active_devices_uses_dhcp_active_class_id_for_type() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {"id": "*1", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:01"},
            {"id": "*2", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:02"},
            {"id": "*3", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:03"},
            {"id": "*4", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:04"},
        ],
        leases=[
            {
                "mac-address": "AA:BB:CC:DD:EE:01",
                "host-name": "generic-one",
                "class-id": "HUAWEI:android:VOG",
            },
            {
                "mac-address": "AA:BB:CC:DD:EE:02",
                "host-name": "generic-two",
                "class-id": "MSFT 5.0\x00",
            },
            {
                "mac-address": "AA:BB:CC:DD:EE:03",
                "host-name": "generic-three",
                "class-id": "chromeos",
            },
            {
                "active-mac-address": "AA:BB:CC:DD:EE:04",
                "host-name": "generic-four",
                "class-id": "Linux 4.14.90 mips",
            },
        ],
    )

    devices = client.get_hotspot_active_devices("alice")

    assert [device["device-type"] for device in devices] == [
        "Phone",
        "PC",
        "Chromebook",
        "Linux device",
    ]
    assert [device["class-id"] for device in devices] == [
        "HUAWEI:android:VOG",
        "MSFT 5.0",
        "chromeos",
        "Linux 4.14.90 mips",
    ]


def test_get_hotspot_active_devices_caches_dhcp_leases_for_client_lifetime() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    fake_api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:01",
            },
        ],
        leases=[
            {
                "mac-address": "AA:BB:CC:DD:EE:01",
                "host-name": "Alice-iPhone",
            },
        ],
    )
    client._api = fake_api

    first_devices = client.get_hotspot_active_devices("alice")
    fake_api.lease_resource.records.clear()
    second_devices = client.get_hotspot_active_devices("alice")

    assert first_devices[0]["device-name"] == "Alice-iPhone"
    assert second_devices[0]["device-name"] == "Alice-iPhone"


def test_infer_device_type_from_common_device_names_and_platforms() -> None:
    assert infer_device_type("Alice-iPhone") == "Phone"
    assert infer_device_type("Galaxy-S24") == "Phone"
    assert infer_device_type("DESKTOP-ABC123") == "PC"
    assert infer_device_type("Johns-MacBook-Pro") == "PC"
    assert infer_device_type("Family-iPad") == "Tablet"
    assert infer_device_type("generic-host", "Android") == "Phone"
    assert infer_device_type("generic-host") == "Unknown"


def test_infer_device_type_prefers_specific_tablet_and_computer_names() -> None:
    assert infer_device_type("Samsung-Galaxy-Tab-S9", "Android") == "Tablet"
    assert infer_device_type("Samsung-Galaxy-Book") == "PC"


def test_infer_device_type_prioritizes_dhcp_active_class_id() -> None:
    assert infer_device_type("DESKTOP-looking-name", active_class_id="android-dhcp-16") == "Phone"
    assert infer_device_type("Alice-iPhone", active_class_id="MSFT 5.0") == "PC"
    assert infer_device_type("generic-host", active_class_id="chromeos") == "Chromebook"
    assert (
        infer_device_type("generic-host", active_class_id="Linux 4.14.90 mips")
        == "Linux device"
    )


def test_get_hotspot_user_falls_back_to_case_insensitive_lookup() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [],
        users=[
            {
                "name": "alice",
                "comment": "Parent account",
            }
        ],
    )

    user = client.get_hotspot_user("  ALICE  ")

    assert user == {
        "name": "alice",
        "comment": "Parent account",
    }


def test_get_hotspot_user_usage_combines_user_and_active_session_totals() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "bytes-in": "100",
                "bytes-out": "200",
            },
            {
                "id": "*2",
                "user": "alice",
                "bytes-in": "300",
                "bytes-out": "400",
            },
        ],
        users=[
            {
                "name": "alice",
                "comment": "Parent account",
                "bytes-in": "500",
                "bytes-out": "1000",
                "limit-bytes-in": "2000",
                "limit-bytes-out": "3000",
                "limit-bytes-total": "7000",
            }
        ],
    )

    usage = client.get_hotspot_user_usage("alice")

    assert usage == {
        "username": "alice",
        "user_comment": "Parent account",
        "user_bytes_in": 500,
        "user_bytes_out": 1000,
        "user_bytes_total": 1500,
        "active_bytes_in": 400,
        "active_bytes_out": 600,
        "active_bytes_total": 1000,
        "combined_bytes_in": 900,
        "combined_bytes_out": 1600,
        "combined_bytes_total": 2500,
        "limit_bytes_in": 2000,
        "limit_bytes_out": 3000,
        "limit_bytes_total": 7000,
    }


def test_remove_hotspot_active_device_removes_only_selected_session() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    fake_api = FakeApi(
        [
            {"id": "*1", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:01"},
            {"id": "*2", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:02"},
            {"id": "*3", "user": "bob", "mac-address": "AA:BB:CC:DD:EE:03"},
        ]
    )
    client._api = fake_api

    removed = client.remove_hotspot_active_device("alice", "*2")

    assert removed is True
    assert fake_api.active_resource.removed_ids == ["*2"]
    assert fake_api.active_resource.get(user="alice") == [
        {"id": "*1", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:01"}
    ]


def test_remove_hotspot_active_device_returns_false_for_non_matching_session() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    fake_api = FakeApi(
        [
            {"id": "*1", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:01"},
            {"id": "*2", "user": "bob", "mac-address": "AA:BB:CC:DD:EE:02"},
        ]
    )
    client._api = fake_api

    removed = client.remove_hotspot_active_device("alice", "*2")

    assert removed is False
    assert fake_api.active_resource.removed_ids == []
    assert fake_api.active_resource.get() == [
        {"id": "*1", "user": "alice", "mac-address": "AA:BB:CC:DD:EE:01"},
        {"id": "*2", "user": "bob", "mac-address": "AA:BB:CC:DD:EE:02"},
    ]


def test_remove_hotspot_active_device_falls_back_to_mac_address_lookup() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    fake_api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:01",
                "address": "10.0.0.2",
            },
            {
                "id": "*2",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:02",
                "address": "10.0.0.3",
            },
        ]
    )
    client._api = fake_api

    removed = client.remove_hotspot_active_device(
        "alice",
        "*missing",
        mac_address="AA:BB:CC:DD:EE:02",
    )

    assert removed is True
    assert fake_api.active_resource.removed_ids == ["*2"]


def test_remove_hotspot_active_device_falls_back_to_ip_address_lookup() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    fake_api = FakeApi(
        [
            {
                "id": "*1",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:01",
                "address": "10.0.0.2",
            },
            {
                "id": "*2",
                "user": "alice",
                "mac-address": "AA:BB:CC:DD:EE:02",
                "address": "10.0.0.3",
            },
        ]
    )
    client._api = fake_api

    removed = client.remove_hotspot_active_device(
        "alice",
        "*missing",
        ip_address="10.0.0.3",
    )

    assert removed is True
    assert fake_api.active_resource.removed_ids == ["*2"]


def test_get_hotspot_total_bytes_used_matches_routeros_script_logic() -> None:
    client = MikroTikClient(
        MikroTikConfig(host="router", username="admin", password="secret")
    )
    client._api = FakeApi(
        [
            {"user": "alice", "bytes-in": "100", "bytes-out": "200"},
            {"user": "alice", "bytes-in": "300", "bytes-out": "400"},
        ],
        users=[
            {
                "name": "alice",
                "bytes-in": "500",
                "bytes-out": "1000",
            }
        ],
    )

    assert client.get_hotspot_total_bytes_used("alice") == 2500
