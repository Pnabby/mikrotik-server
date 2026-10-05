import base64
import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from routeros_api.exceptions import RouterOsApiError

from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.dependencies import get_mikrotik_client, resolve_router
from app.integrations.mikrotik.registry import RouterDefinition
from app.integrations.mikrotik.wireguard import BTH_PATH, PEER_PATH, WireGuardManager
from app.main import create_app
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_wireguard import (
    BthPeerCreate,
    RouterRestartRequest,
    StaticPeerCreate,
    WireGuardPeerAction,
)
from app.services.admin_wireguard import AdminWireGuardService


class Resource:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or []
        self.fail = fail
        self.writes = []
        self.calls = []
        self.adds = []
        self.config = None
        self.legacy_export = False

    def get(self):
        if self.fail:
            raise RouterOsApiError("secret-router-error")
        return deepcopy(self.rows)

    def set(self, **values):
        if self.fail:
            raise RouterOsApiError("secret-router-error")
        self.writes.append(values)
        row = next(
            item for item in self.rows if (item.get("id") or item.get(".id")) == values["id"]
        )
        row.update({key: value for key, value in values.items() if key != "id"})

    def call(self, command, arguments):
        if self.fail:
            raise RouterOsApiError("secret-router-error")
        self.calls.append((command, arguments))
        if command == "show-client-config":
            if self.legacy_export and "show-sensitive" in arguments:
                raise RouterOsApiError("unknown parameter")
            return [{"conf": self.config}] if self.config is not None else []
        return []

    def add(self, **arguments):
        if self.fail:
            raise RouterOsApiError("secret-router-error")
        self.adds.append(arguments)
        row = {"id": "*F", **arguments}
        row["private-key"] = TEST_PRIVATE_KEY
        self.rows.append(row)
        return SimpleNamespace(done_message={"ret": "*F"})


TEST_PRIVATE_KEY = base64.b64encode(bytes(range(32))).decode()
TEST_PUBLIC_KEY = base64.b64encode(bytes(range(32, 64))).decode()
CLIENT_CONFIG = (
    f"[Interface]\nPrivateKey = {TEST_PRIVATE_KEY}\nAddress = 192.168.216.2/32\n"
    f"[Peer]\nPublicKey = {TEST_PUBLIC_KEY}\nAllowedIPs = 0.0.0.0/0, ::/0\n"
    "Endpoint = router.vpn.example:13231\nPersistentKeepalive = 30\n"
)


class RouterClient:
    def __init__(self):
        self.resources = {
            "/interface/wireguard": Resource(
                [
                    {
                        "id": "*1",
                        "name": "back-to-home-vpn",
                        "public-key": "router-public",
                        "private-key": "interface-private",
                        "listen-port": "13231",
                        "mtu": "1420",
                        "disabled": "false",
                        "running": "true",
                    }
                ]
            ),
            PEER_PATH: Resource(
                [
                    {
                        "id": "*A",
                        "name": "Laptop",
                        "interface": "wg-admin",
                        "public-key": "laptop-public",
                        "preshared-key": "peer-secret",
                        "private-key": "peer-private",
                        "allowed-address": "10.0.0.2/32",
                        "last-handshake": "1m5s",
                        "rx": "1024",
                        "tx": "2048",
                        "persistent-keepalive": "00:00:25",
                        "endpoint-address": "example.test",
                        "endpoint-port": "1234",
                        "current-endpoint-address": "2001:db8::1",
                        "current-endpoint-port": "5678",
                    },
                    {
                        "id": "*B",
                        "name": "Same name",
                        "interface": "back-to-home-vpn",
                        "dynamic": "true",
                        "public-key": "bth-public",
                        "last-handshake": "0s",
                    },
                    {
                        "id": "*C",
                        "dynamic": "yes",
                        "interface": "back-to-home-vpn",
                        "public-key": "unmapped-public",
                        "name": "Phone",
                    },
                ]
            ),
            BTH_PATH: Resource(
                [
                    {
                        "id": "*D",
                        "name": "Phone",
                        "public-key": "bth-public",
                        "private-key": "bth-private",
                        "file-access-token": "file-secret",
                        "client-address": "192.168.216.2/32",
                        "active": "yes",
                        "allow-lan": "no",
                        "expires": "never",
                    },
                    {
                        ".id": "*E",
                        "name": "Phone",
                        "public-key": "disabled-public",
                        "disabled": "true",
                        "active": "false",
                        "expires": "2026-10-01 00:00:00",
                    },
                ]
            ),
            "/ip/cloud": Resource(
                [
                    {
                        "vpn-status": "running",
                        "vpn-dns-name": "router.vpn.example",
                        "vpn-port": "13231",
                        "vpn-relay-ipv4-status": "reachable directly",
                        "vpn-private-key": "cloud-private",
                        "dns-name": "router.example",
                    }
                ]
            ),
            "/": Resource(),
        }
        self.connections = 0

    def connect(self):
        self.connections += 1
        return self

    def get_resource(self, path):
        return self.resources[path]


class AuditSession:
    def __init__(self):
        self.audits = []
        self.commits = 0

    def add(self, audit):
        self.audits.append(audit)

    def commit(self):
        self.commits += 1


@pytest.fixture
def client():
    return RouterClient()


@pytest.fixture
def definition():
    return RouterDefinition("hall", "Hall", "router.example", 8728, "192.168.88.0/24")


def test_snapshot_matches_bth_by_public_key_and_includes_disabled_users(client, definition):
    result = WireGuardManager(client).snapshot(definition)
    peers = {peer.id: peer for peer in result.peers}
    assert len(peers) == 4
    assert peers["bth:*D"].managed_by == "bth"
    assert peers["bth:*D"].name == "Phone"
    assert peers["bth:*D"].can_manage
    assert not peers["bth:*D"].allow_lan
    assert peers["bth:*E"].disabled
    assert peers["bth:*E"].expires == "2026-10-01 00:00:00"
    assert peers["peer:*C"].managed_by == "dynamic"
    assert not peers["peer:*C"].can_manage
    regular = peers["peer:*A"]
    assert regular.last_handshake_seconds == 65
    assert regular.current_endpoint == "[2001:db8::1]:5678"
    assert regular.keepalive_seconds == 25
    assert regular.rx_bytes == 1024
    assert regular.tx_bytes == 2048
    assert result.cloud.vpn_dns_name == "router.vpn.example"
    assert result.interfaces[0].running
    serialized = result.model_dump_json()
    for secret in (
        "interface-private",
        "peer-secret",
        "peer-private",
        "bth-private",
        "file-secret",
        "cloud-private",
        "private-key",
        "preshared-key",
    ):
        assert secret not in serialized


@pytest.mark.parametrize(
    "raw,rx,expected",
    [
        (None, "1024", None),
        ("never", "1024", None),
        ("0s", "0", None),
        ("00:00:00", "0", None),
        ("0s", "1024", 0),
        ("5", "0", 5),
        ("1d02:03:04", "1", 93784),
    ],
)
def test_handshake_age_does_not_invent_a_connection(raw, rx, expected):
    result = WireGuardManager._peer({"id": "*A", "last-handshake": raw, "rx": rx}, None)
    assert result.last_handshake_seconds == expected


@pytest.mark.parametrize("path", [BTH_PATH, "/ip/cloud"])
def test_optional_bth_and_cloud_failures_leave_wireguard_visible(client, definition, path):
    client.resources[path].fail = True
    result = WireGuardManager(client).snapshot(definition)
    assert result.interfaces
    assert result.peers
    assert result.warnings
    assert "secret-router-error" not in result.model_dump_json()
    if path == BTH_PATH:
        assert not next(peer for peer in result.peers if peer.id == "peer:*B").can_manage
    else:
        assert result.cloud is None


@pytest.mark.parametrize(
    "target,path,item_id",
    [
        ("peer:*A", PEER_PATH, "*A"),
        ("bth:*D", BTH_PATH, "*D"),
        ("bth:*E", BTH_PATH, "*E"),
    ],
)
def test_reset_queues_both_steps_on_router_without_separate_disable_request(
    client,
    target,
    path,
    item_id,
):
    result = WireGuardManager(client).apply(target, WireGuardPeerAction(action="reset"))
    assert result.queued
    assert client.resources[path].writes == []
    command, args = client.resources["/"].calls[0]
    assert command == "execute"
    assert args["script"] == (
        f":delay 2s; {path}/set {item_id} disabled=yes; "
        f":delay 1s; {path}/set {item_id} disabled=no;"
    )
    assert "private-key" not in args["script"]


@pytest.mark.parametrize("target", ["peer:*A; /system/reboot", "peer:0", "bth:Phone", "x:*A"])
def test_reset_rejects_script_injection_and_nonopaque_ids(client, target):
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).apply(target, WireGuardPeerAction(action="reset"))
    assert error.value.status_code == 404
    assert client.connections == 0


@pytest.mark.parametrize("target,status", [("peer:*C", 409), ("peer:*FF", 404)])
def test_unmanaged_or_removed_peers_cannot_be_mutated(client, target, status):
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).apply(target, WireGuardPeerAction(action="disable"))
    assert error.value.status_code == status
    assert not client.resources[PEER_PATH].writes


def test_enable_disabled_bth_user_and_change_lan_access_without_changing_keys(client):
    manager = WireGuardManager(client)
    manager.apply("bth:*E", WireGuardPeerAction(action="enable"))
    manager.apply("bth:*D", WireGuardPeerAction(action="allow_lan", allow_lan=True))
    assert client.resources[BTH_PATH].writes == [
        {"id": "*E", "disabled": "no"},
        {"id": "*D", "allow-lan": "yes"},
    ]


def test_keepalive_is_router_side_and_bth_settings_are_protected(client):
    manager = WireGuardManager(client)
    manager.apply("peer:*A", WireGuardPeerAction(action="keepalive", keepalive_seconds=25))
    assert client.resources[PEER_PATH].writes == [{"id": "*A", "persistent-keepalive": "25s"}]
    with pytest.raises(ServiceError) as error:
        manager.apply("bth:*D", WireGuardPeerAction(action="keepalive", keepalive_seconds=25))
    assert error.value.error_code == "VPN_BTH_KEEPALIVE"
    with pytest.raises(ServiceError):
        manager.apply("peer:*A", WireGuardPeerAction(action="allow_lan", allow_lan=True))


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "revoke"},
        {"action": "reset", "private_key": "new-key"},
        {"action": "keepalive"},
        {"action": "keepalive", "keepalive_seconds": -1},
        {"action": "keepalive", "keepalive_seconds": 65536},
        {"action": "keepalive", "keepalive_seconds": True},
        {"action": "keepalive", "keepalive_seconds": 2.5},
        {"action": "reset", "keepalive_seconds": 25},
        {"action": "allow_lan"},
        {"action": "allow_lan", "allow_lan": "yes"},
        {"action": "reset", "allow_lan": False},
    ],
)
def test_action_validation_limits_mutations(payload):
    with pytest.raises(ValidationError):
        WireGuardPeerAction(**payload)


def test_actions_are_audited_including_unconfirmed_resets(client):
    session = AuditSession()
    admin = SimpleNamespace(id=uuid.uuid4())
    service = AdminWireGuardService(session, WireGuardManager(client))
    service.action("hall", "peer:*A", WireGuardPeerAction(action="reset"), admin, "127.0.0.1")
    assert session.audits[0].details["outcome"] == "queued"
    assert session.audits[0].admin_user_id == admin.id
    assert session.commits == 2
    client.resources["/"].fail = True
    with pytest.raises(ServiceError) as error:
        service.action("hall", "peer:*A", WireGuardPeerAction(action="reset"), admin, None)
    assert error.value.error_code == "VPN_ACTION_UNCONFIRMED"
    assert "secret-router-error" not in error.value.detail
    assert session.audits[-1].details["outcome"] == "unconfirmed"


def test_database_audit_failure_prevents_router_mutation(client):
    class FailingAuditSession(AuditSession):
        def commit(self):
            raise RuntimeError("Database unavailable")

    service = AdminWireGuardService(FailingAuditSession(), WireGuardManager(client))
    with pytest.raises(RuntimeError):
        service.action(
            "hall",
            "peer:*A",
            WireGuardPeerAction(action="disable"),
            SimpleNamespace(id=uuid.uuid4()),
            None,
        )
    assert client.connections == 0


@pytest.fixture
def api(client, definition):
    application = create_app()
    session = AuditSession()
    application.dependency_overrides[get_db_session] = lambda: session
    application.dependency_overrides[resolve_router] = lambda: definition
    application.dependency_overrides[get_mikrotik_client] = lambda: client
    return application, TestClient(application), session


def test_wireguard_endpoints_require_admin_authentication(api, client):
    _, http, _ = api
    assert http.get("/api/admin/hostels/hall/wireguard").status_code == 401
    assert (
        http.post(
            "/api/admin/hostels/hall/wireguard/peers/peer:*A/action", json={"action": "reset"}
        ).status_code
        == 401
    )
    assert client.connections == 0


def test_viewers_can_inspect_but_cannot_mutate(api, client):
    app, http, session = api
    app.dependency_overrides[get_authenticated_admin] = lambda: SimpleNamespace(
        id=uuid.uuid4(),
        role=AdminRole.VIEWER,
    )
    response = http.get("/api/admin/hostels/hall/wireguard")
    assert response.status_code == 200
    assert len(response.json()["peers"]) == 4
    connections = client.connections
    for action in ("reset", "disable", "enable"):
        response = http.post(
            "/api/admin/hostels/hall/wireguard/peers/peer:*A/action", json={"action": action}
        )
        assert response.status_code == 403
    assert client.connections == connections
    assert not session.audits


def test_operator_reset_response_is_queued_and_router_errors_are_sanitized(api, client):
    app, http, session = api
    app.dependency_overrides[get_authenticated_admin] = lambda: SimpleNamespace(
        id=uuid.uuid4(),
        role=AdminRole.OPERATOR,
    )
    url = "/api/admin/hostels/hall/wireguard/peers/bth:*D/action"
    response = http.post(url, json={"action": "reset"})
    assert response.status_code == 200
    assert response.json()["queued"]
    assert session.audits[-1].details["target"] == "bth:*D"
    client.resources["/"].fail = True
    response = http.post(url, json={"action": "reset"})
    assert response.status_code == 502
    assert response.json()["code"] == "VPN_ACTION_UNCONFIRMED"
    assert "secret-router-error" not in response.text


def static_payload(**overrides):
    values = {
        "kind": "wireguard",
        "name": "New laptop",
        "interface": "wg-admin",
        "client_addresses": "10.0.0.3/32",
        "client_endpoint": "router.example",
        "client_allowed_addresses": "192.168.88.0/24",
        "client_dns": "1.1.1.1",
    }
    values.update(overrides)
    return StaticPeerCreate(**values)


def enable_regular_interface(client):
    client.resources["/interface/wireguard"].rows.append(
        {
            "id": "*2",
            "name": "wg-admin",
            "disabled": "false",
            "listen-port": "13231",
        }
    )


def test_create_bth_user_uses_router_generated_keys_and_expiry(client):
    result = WireGuardManager(client).create(
        BthPeerCreate(
            kind="bth",
            name="New phone",
            allow_lan=True,
            expires_days=7,
            client_allowed_addresses="192.168.88.0/24",
            client_dns="1.1.1.1",
        )
    )
    assert result.peer_id == "bth:*F"
    assert client.resources[BTH_PATH].adds == [
        {
            "comment": "New phone",
            "disabled": "no",
            "name": "New phone",
            "allow-lan": "yes",
            "expires": "7d",
            "client-allowed-address": "192.168.88.0/24",
            "client-dns": "1.1.1.1",
        }
    ]
    assert not client.resources[PEER_PATH].adds


def test_bth_creation_requires_running_bth_and_unique_device_name(client):
    manager = WireGuardManager(client)
    with pytest.raises(ServiceError) as error:
        manager.create(BthPeerCreate(kind="bth", name="Phone"))
    assert error.value.error_code == "VPN_DUPLICATE_NAME"
    client.resources["/ip/cloud"].rows[0]["vpn-status"] = "stopped"
    with pytest.raises(ServiceError) as error:
        manager.create(BthPeerCreate(kind="bth", name="New phone"))
    assert error.value.error_code == "VPN_BTH_NOT_RUNNING"
    assert not client.resources[BTH_PATH].adds


def test_create_regular_peer_sets_client_export_fields_and_separate_key(client):
    enable_regular_interface(client)
    result = WireGuardManager(client).create(static_payload())
    assert result.peer_id == "peer:*F"
    assert client.resources[PEER_PATH].adds == [
        {
            "comment": "New laptop",
            "disabled": "no",
            "interface": "wg-admin",
            "private-key": "auto",
            "allowed-address": "10.0.0.3/32",
            "client-address": "10.0.0.3/32",
            "client-endpoint": "router.example",
            "client-keepalive": "25s",
            "client-allowed-address": "192.168.88.0/24",
            "client-dns": "1.1.1.1",
        }
    ]
    assert not client.resources["/interface/wireguard"].writes
    assert not client.resources["/"].calls


@pytest.mark.parametrize("address", ["10.0.0.2/32", "10.0.0.10/32"])
def test_regular_creation_rejects_overlap_including_existing_subnets(client, address):
    enable_regular_interface(client)
    client.resources[PEER_PATH].rows[0]["allowed-address"] = "10.0.0.0/24"
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).create(static_payload(client_addresses=address))
    assert error.value.error_code == "VPN_ADDRESS_CONFLICT"
    assert not client.resources[PEER_PATH].adds


@pytest.mark.parametrize(
    "interface,code",
    [
        ("missing", "VPN_INTERFACE_UNAVAILABLE"),
        ("back-to-home-vpn", "VPN_USE_BTH"),
    ],
)
def test_regular_creation_requires_enabled_regular_interface(client, interface, code):
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).create(static_payload(interface=interface))
    assert error.value.error_code == code
    assert not client.resources[PEER_PATH].adds


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "\nNew peer"},
        {"name": "peer\n/system/reboot"},
        {"client_addresses": "10.0.0.0/24"},
        {"client_addresses": "::/0"},
        {"client_addresses": "10.0.0.3/32,10.0.0.4/32"},
        {"client_addresses": "0.0.0.0/32"},
        {"client_endpoint": "host:13231"},
        {"client_endpoint": "host\nEndpoint = other.test:5"},
        {"client_endpoint": "https://router.example"},
        {"client_endpoint": "0.0.0.0"},
        {"client_allowed_addresses": "garbage"},
        {"client_dns": "1.1.1.1\nPrivateKey=x"},
        {"client_keepalive": True},
        {"client_keepalive": 65536},
    ],
)
def test_creation_inputs_cannot_inject_config_fields_or_broad_client_addresses(overrides):
    with pytest.raises(ValidationError):
        static_payload(**overrides)


def test_create_normalizes_ipv6_endpoint_and_networks():
    payload = static_payload(
        client_endpoint="[2001:db8::1]",
        client_addresses="2001:db8:1::2/128",
        client_allowed_addresses="192.168.88.12/24, ::/0",
    )
    assert payload.client_endpoint == "2001:db8::1"
    assert payload.client_addresses == "2001:db8:1::2/128"
    assert payload.client_allowed_addresses == "192.168.88.0/24,::/0"


def test_native_config_export_preserves_bth_config_and_never_changes_keys(client):
    client.resources[BTH_PATH].config = CLIENT_CONFIG
    result = WireGuardManager(client).client_config("bth:*D")
    assert result.config == CLIENT_CONFIG
    assert result.peer_id == "bth:*D"
    assert client.resources[BTH_PATH].calls == [
        ("show-client-config", {"id": "*D", "show-sensitive": "yes"}),
    ]
    assert not client.resources[BTH_PATH].writes
    assert not client.resources[BTH_PATH].adds
    assert TEST_PRIVATE_KEY not in repr(result)


def test_legacy_read_only_export_fallback(client):
    client.resources[BTH_PATH].config = CLIENT_CONFIG
    client.resources[BTH_PATH].legacy_export = True
    result = WireGuardManager(client).client_config("bth:*D")
    assert result.config == CLIENT_CONFIG
    assert client.resources[BTH_PATH].calls[-1] == ("show-client-config", {"id": "*D"})
    assert not client.resources[BTH_PATH].writes


def test_public_key_alone_does_not_create_a_fake_client_qr(client):
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).client_config("peer:*A")
    assert error.value.error_code == "VPN_CONFIG_UNAVAILABLE"
    assert not client.resources[PEER_PATH].calls
    assert not client.resources[PEER_PATH].writes


def test_regular_export_requires_client_fields_and_preserves_native_config(client):
    row = client.resources[PEER_PATH].rows[0]
    row["private-key"] = TEST_PRIVATE_KEY
    client.resources[PEER_PATH].config = CLIENT_CONFIG
    manager = WireGuardManager(client)
    with pytest.raises(ServiceError):
        manager.client_config("peer:*A")
    row.update({"client-address": "192.168.216.2/32", "client-endpoint": "router.vpn.example"})
    assert manager.client_config("peer:*A").config == CLIENT_CONFIG


def test_creation_with_lost_reply_is_not_retried_and_can_be_found_by_name(client):
    resource = client.resources[BTH_PATH]
    original_add = resource.add

    def lost_reply(**arguments):
        original_add(**arguments)
        raise OSError("Connection closed before reply")

    resource.add = lost_reply
    session = AuditSession()
    service = AdminWireGuardService(session, WireGuardManager(client))
    payload = BthPeerCreate(kind="bth", name="New phone")
    with pytest.raises(ServiceError) as error:
        service.create("hall", payload, SimpleNamespace(id=uuid.uuid4()), None)
    assert error.value.error_code == "VPN_CREATE_UNCONFIRMED"
    assert len(resource.adds) == 1
    assert session.audits[-1].details["outcome"] == "unconfirmed"
    with pytest.raises(ServiceError) as error:
        service.create("hall", payload, SimpleNamespace(id=uuid.uuid4()), None)
    assert error.value.error_code == "VPN_DUPLICATE_NAME"
    assert len(resource.adds) == 1


@pytest.mark.parametrize(
    "config",
    [
        "",
        CLIENT_CONFIG.replace(TEST_PRIVATE_KEY, "***"),
        CLIENT_CONFIG.replace(TEST_PUBLIC_KEY, "***"),
        CLIENT_CONFIG + "PresharedKey = ***\n",
        CLIENT_CONFIG.replace("Endpoint = router.vpn.example:13231\n", ""),
    ],
)
def test_export_rejects_masked_keys_and_incomplete_configs(client, config):
    client.resources[BTH_PATH].config = config
    with pytest.raises(ServiceError) as error:
        WireGuardManager(client).client_config("bth:*D")
    assert error.value.error_code == "VPN_CONFIG_UNAVAILABLE"


def test_restart_requires_selected_router_confirmation_and_is_audited(client, definition):
    session = AuditSession()
    admin = SimpleNamespace(id=uuid.uuid4())
    service = AdminWireGuardService(session, WireGuardManager(client))
    with pytest.raises(ServiceError) as error:
        service.restart(definition, RouterRestartRequest(confirmation="Other Hall"), admin, None)
    assert error.value.status_code == 400
    assert not session.audits
    assert client.connections == 0
    result = service.restart(definition, RouterRestartRequest(confirmation="Hall"), admin, None)
    assert result.queued
    assert client.resources["/"].calls == [("execute", {"script": ":delay 3s; /system/reboot;"})]
    assert session.audits[-1].action == "router.restart_requested"
    assert session.audits[-1].details["outcome"] == "queued"


def test_sensitive_config_response_is_not_cached_and_audit_never_contains_secrets(api, client):
    app, http, session = api
    app.dependency_overrides[get_authenticated_admin] = lambda: SimpleNamespace(
        id=uuid.uuid4(),
        role=AdminRole.OPERATOR,
    )
    client.resources[BTH_PATH].config = CLIENT_CONFIG
    response = http.post("/api/admin/hostels/hall/wireguard/peers/bth:*D/client-config")
    assert response.status_code == 200
    assert response.json()["config"] == CLIENT_CONFIG
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"
    assert session.audits[-1].action == "wireguard.client_config_viewed"
    assert TEST_PRIVATE_KEY not in str(session.audits[-1].details)
    assert "config" not in session.audits[-1].details
    ordinary = http.get("/api/admin/hostels/hall/wireguard")
    assert TEST_PRIVATE_KEY not in ordinary.text


@pytest.mark.parametrize("authenticated", [False, True])
def test_anonymous_and_viewer_cannot_create_export_or_restart(api, client, authenticated):
    app, http, session = api
    if authenticated:
        app.dependency_overrides[get_authenticated_admin] = lambda: SimpleNamespace(
            id=uuid.uuid4(),
            role=AdminRole.VIEWER,
        )
    expected = 403 if authenticated else 401
    responses = [
        http.post("/api/admin/hostels/hall/wireguard/peers", json={"kind": "bth", "name": "New"}),
        http.post("/api/admin/hostels/hall/wireguard/peers/bth:*D/client-config"),
        http.post("/api/admin/hostels/hall/restart", json={"confirmation": "Hall"}),
    ]
    assert all(response.status_code == expected for response in responses)
    assert client.connections == 0
    assert not session.audits


def test_creation_and_restart_http_contract_and_sanitized_failures(api, client):
    app, http, session = api
    app.dependency_overrides[get_authenticated_admin] = lambda: SimpleNamespace(
        id=uuid.uuid4(),
        role=AdminRole.ADMINISTRATOR,
    )
    response = http.post(
        "/api/admin/hostels/hall/wireguard/peers", json={"kind": "bth", "name": "New phone"}
    )
    assert response.status_code == 201
    assert response.json()["peer_id"] == "bth:*F"
    assert session.audits[-1].action == "wireguard.peer_created"
    assert session.audits[-1].details["target"] == "bth:*F"
    # Repeating a creation request cannot silently create another device with
    # the same name after a lost response.
    response = http.post(
        "/api/admin/hostels/hall/wireguard/peers", json={"kind": "bth", "name": "New phone"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VPN_DUPLICATE_NAME"
    response = http.post("/api/admin/hostels/hall/restart", json={"confirmation": "Other Hall"})
    assert response.status_code == 400
    client.resources["/"].fail = True
    response = http.post("/api/admin/hostels/hall/restart", json={"confirmation": "Hall"})
    assert response.status_code == 502
    assert response.json()["code"] == "VPN_RESTART_UNCONFIRMED"
    assert "secret-router-error" not in response.text
    assert session.audits[-1].details["outcome"] == "unconfirmed"
