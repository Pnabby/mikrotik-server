from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from datetime import UTC, datetime

from fastapi import status
from routeros_api.exceptions import RouterOsApiError

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.client import MikroTikClient, _parse_routeros_duration
from app.integrations.mikrotik.registry import RouterDefinition
from app.schemas.admin_wireguard import (
    WireGuardActionResult,
    WireGuardClientConfig,
    WireGuardCloud,
    WireGuardCreateResult,
    WireGuardInterface,
    WireGuardPeer,
    WireGuardPeerAction,
    WireGuardPeerCreate,
    WireGuardSnapshot,
)

PEER_PATH = "/interface/wireguard/peers"
BTH_PATH = "/ip/cloud/back-to-home-user"


def _valid_key(value: object) -> bool:
    try:
        return len(base64.b64decode(str(value or ""), validate=True)) == 32
    except (ValueError, binascii.Error):
        return False


def _true(value: object) -> bool:
    return str(value).strip().casefold() in {"yes", "true", "1", "on"}


def _integer(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except (ValueError, TypeError):
        return 0


def _duration(value: object) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else _parse_routeros_duration(value)


def _id(row: dict) -> str:
    return str(row.get("id") or row.get(".id") or "")


def _endpoint(address: object, port: object) -> str:
    host = str(address or "").strip()
    if not host or host in {"0.0.0.0", "::"}:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{_integer(port)}" if _integer(port) else host


class WireGuardManager:
    def __init__(self, client: MikroTikClient) -> None:
        self.client = client

    def snapshot(self, router: RouterDefinition) -> WireGuardSnapshot:
        api = self.client.connect()
        interface_rows = api.get_resource("/interface/wireguard").get()
        peer_rows = api.get_resource(PEER_PATH).get()
        warnings = []
        cloud = None
        try:
            rows = api.get_resource("/ip/cloud").get()
            row = rows[0] if rows else {}
            cloud = WireGuardCloud(
                vpn_status=row.get("vpn-status") or "Unknown",
                vpn_dns_name=row.get("vpn-dns-name") or "",
                vpn_port=_integer(row.get("vpn-port")),
                dns_name=row.get("dns-name") or "",
                public_address=row.get("public-address") or "",
                relay_ipv4_status=row.get("vpn-relay-ipv4-status") or "",
                relay_ipv6_status=row.get("vpn-relay-ipv6-status") or "",
            )
        except RouterOsApiError:
            warnings.append("IP Cloud status is unavailable. Check RouterOS API permissions.")
        bth_rows = []
        # BTH is optional on older RouterOS versions and unsupported hardware.
        try:
            bth_rows = api.get_resource(BTH_PATH).get()
        except RouterOsApiError:
            warnings.append(
                "Back to Home users are unavailable on this RouterOS version or API account. "
                "Dynamic peers without a matching BTH user cannot be changed here."
            )
        users_by_key = {row["public-key"]: row for row in bth_rows if row.get("public-key")}
        matched_ids = set()
        peers = []
        for row in peer_rows:
            # Match cryptographic identity, never a possibly duplicated user name.
            user = users_by_key.get(row.get("public-key"))
            if user is not None:
                matched_ids.add(_id(user))
            peers.append(self._peer(row, user))
        # Disabled/expired BTH users can have no dynamic WireGuard peer at all.
        for user in bth_rows:
            if _id(user) not in matched_ids:
                peers.append(self._peer({}, user))
        return WireGuardSnapshot(
            router_id=router.router_id,
            router_name=router.name,
            generated_at=datetime.now(UTC),
            interfaces=[
                WireGuardInterface(
                    name=row.get("name") or "",
                    public_key=row.get("public-key") or "",
                    listen_port=_integer(row.get("listen-port")),
                    mtu=_integer(row.get("mtu")),
                    disabled=_true(row.get("disabled")),
                    running=_true(row.get("running")),
                )
                for row in interface_rows
            ],
            peers=peers,
            cloud=cloud,
            warnings=warnings,
        )

    @staticmethod
    def _peer(row: dict, user: dict | None) -> WireGuardPeer:
        source = user if user is not None else row
        managed_by = (
            "bth" if user is not None else ("dynamic" if _true(row.get("dynamic")) else "wireguard")
        )
        prefix = "bth" if user is not None else "peer"
        raw_handshake = str(row.get("last-handshake") or "").strip()
        # RouterOS reports an empty/zero duration before any successful handshake.
        age = _duration(raw_handshake)
        handshake = (
            age
            if raw_handshake
            and raw_handshake.casefold() != "never"
            and (age or _integer(row.get("rx")))
            else None
        )
        return WireGuardPeer(
            id=f"{prefix}:{_id(source)}",
            name=source.get("comment") or source.get("name") or _id(source),
            interface=row.get("interface") or ("back-to-home-vpn" if user is not None else ""),
            public_key=source.get("public-key") or "",
            allowed_addresses=row.get("allowed-address") or source.get("client-address") or "",
            endpoint=_endpoint(row.get("endpoint-address"), row.get("endpoint-port")),
            current_endpoint=_endpoint(
                row.get("current-endpoint-address"), row.get("current-endpoint-port")
            ),
            last_handshake_seconds=handshake,
            rx_bytes=_integer(row.get("rx")),
            tx_bytes=_integer(row.get("tx")),
            keepalive_seconds=_duration(row.get("persistent-keepalive")),
            disabled=_true(source.get("disabled")),
            dynamic=_true(row.get("dynamic")) or user is not None,
            managed_by=managed_by,
            can_manage=managed_by != "dynamic"
            and bool(re.fullmatch(r"\*[0-9A-Fa-f]+", _id(source))),
            can_export=user is not None
            or (managed_by == "wireguard" and _valid_key(row.get("private-key"))),
            allow_lan=_true(user.get("allow-lan")) if user is not None else None,
            expires=str(user.get("expires") or "never") if user is not None else None,
            bth_active=_true(user.get("active")) if user is not None else None,
        )

    def _target(self, target: str):
        match = re.fullmatch(r"(peer|bth):(\*[0-9A-Fa-f]+)", target)
        if not match:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Peer not found.")
        kind, item_id = match.groups()
        path = BTH_PATH if kind == "bth" else PEER_PATH
        resource = self.client.connect().get_resource(path)
        row = next((row for row in resource.get() if _id(row) == item_id), None)
        if row is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Peer no longer exists.")
        if kind == "peer" and _true(row.get("dynamic")):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Manage the owning BTH user.",
                error_code="VPN_DYNAMIC_PEER",
            )
        return kind, item_id, path, resource, row

    def create(self, payload: WireGuardPeerCreate) -> WireGuardCreateResult:
        api = self.client.connect()
        path = BTH_PATH if payload.kind == "bth" else PEER_PATH
        resource = api.get_resource(path)
        existing = resource.get()
        if any(
            str(row.get("comment") or row.get("name") or "").casefold() == payload.name.casefold()
            for row in existing
        ):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Use a different device name.",
                error_code="VPN_DUPLICATE_NAME",
            )
        arguments = {"comment": payload.name, "disabled": "no"}
        if payload.kind == "bth":
            cloud_rows = api.get_resource("/ip/cloud").get()
            if not cloud_rows or cloud_rows[0].get("vpn-status") != "running":
                raise ServiceError(
                    status.HTTP_409_CONFLICT,
                    "Back to Home must be running.",
                    error_code="VPN_BTH_NOT_RUNNING",
                )
            arguments.update(
                {
                    "name": payload.name,
                    "allow-lan": "yes" if payload.allow_lan else "no",
                    "expires": f"{payload.expires_days}d" if payload.expires_days else "never",
                    "client-allowed-address": payload.client_allowed_addresses,
                }
            )
        else:
            interfaces = api.get_resource("/interface/wireguard").get()
            iface = next((row for row in interfaces if row.get("name") == payload.interface), None)
            if iface is None or _true(iface.get("disabled")):
                raise ServiceError(
                    status.HTTP_409_CONFLICT,
                    "Choose an enabled WireGuard interface.",
                    error_code="VPN_INTERFACE_UNAVAILABLE",
                )
            if payload.interface == "back-to-home-vpn":
                raise ServiceError(
                    status.HTTP_409_CONFLICT,
                    "Use a Back to Home user here.",
                    error_code="VPN_USE_BTH",
                )
            requested = [ipaddress.ip_network(item) for item in payload.client_addresses.split(",")]
            for row in existing:
                if row.get("interface") != payload.interface:
                    continue
                for raw in str(row.get("allowed-address") or "").split(","):
                    if not raw.strip():
                        continue
                    network = ipaddress.ip_network(raw.strip(), strict=False)
                    if any(
                        item.version == network.version and item.overlaps(network)
                        for item in requested
                    ):
                        raise ServiceError(
                            status.HTTP_409_CONFLICT,
                            "Client address overlaps a peer.",
                            error_code="VPN_ADDRESS_CONFLICT",
                        )
            arguments.update(
                {
                    "interface": payload.interface,
                    "private-key": "auto",
                    "allowed-address": payload.client_addresses,
                    "client-address": payload.client_addresses,
                    "client-endpoint": payload.client_endpoint,
                    "client-keepalive": f"{payload.client_keepalive}s",
                    "client-allowed-address": payload.client_allowed_addresses,
                }
            )
        if payload.client_dns:
            arguments["client-dns"] = payload.client_dns
        # One add command generates a separate client keypair on the router.
        # No retry or read-back after add: a lost reply can mean it already exists.
        result = resource.add(**arguments)
        item_id = str(getattr(result, "done_message", {}).get("ret") or "")
        return WireGuardCreateResult(
            message="Peer created. Import its QR code or configuration on one device.",
            peer_id=f"{'bth' if payload.kind == 'bth' else 'peer'}:{item_id}"
            if re.fullmatch(r"\*[0-9A-Fa-f]+", item_id)
            else None,
        )

    def client_config(self, target: str) -> WireGuardClientConfig:
        kind, item_id, _path, resource, row = self._target(target)
        if kind == "peer" and (
            not _valid_key(row.get("private-key"))
            or not row.get("client-address")
            or not row.get("client-endpoint")
        ):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The client private key is unavailable.",
                error_code="VPN_CONFIG_UNAVAILABLE",
            )
        try:
            rows = resource.call("show-client-config", {"id": item_id, "show-sensitive": "yes"})
        except RouterOsApiError:
            # Older versions do not accept show-sensitive. This read-only fallback
            # never regenerates a key or writes an export file to the router.
            rows = resource.call("show-client-config", {"id": item_id})
        configs = [str(item.get("conf") or "") for item in rows if item.get("conf")]
        done = getattr(rows, "done_message", {})
        if not configs and done.get("conf"):
            configs = [str(done["conf"])]
        config = configs[0] if configs else ""
        private = re.search(r"(?m)^\s*PrivateKey\s*=\s*([^\r\n]+)", config)
        # Do not show a scannable but unusable config with a hidden/missing key.
        if not config or len(config) > 16384 or not private or not _valid_key(private[1].strip()):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A complete config could not be exported.",
                error_code="VPN_CONFIG_UNAVAILABLE",
            )
        other_keys = re.findall(r"(?m)^\s*(?:PublicKey|PresharedKey)\s*=\s*([^\r\n]+)", config)
        if any(not _valid_key(key.strip()) for key in other_keys):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "An exported key is hidden or invalid.",
                error_code="VPN_CONFIG_UNAVAILABLE",
            )
        if not all(
            re.search(pattern, config, re.MULTILINE)
            for pattern in (
                r"^\s*\[Interface\]",
                r"^\s*\[Peer\]",
                r"^\s*Address\s*=\s*\S",
                r"^\s*PublicKey\s*=\s*\S",
                r"^\s*AllowedIPs\s*=\s*\S",
                r"^\s*Endpoint\s*=\s*\S",
            )
        ):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Incomplete client configuration.",
                error_code="VPN_CONFIG_UNAVAILABLE",
            )
        return WireGuardClientConfig(
            peer_id=target, name=row.get("comment") or row.get("name") or item_id, config=config
        )

    def restart(self) -> WireGuardActionResult:
        # Return the queue acknowledgement before reboot closes the API socket.
        self.client.connect().get_resource("/").call(
            "execute",
            {"script": ":delay 3s; /system/reboot;"},
        )
        return WireGuardActionResult(
            message="Router restart queued. WiFi and VPN connections will drop briefly. "
            "This page will keep checking for the router to return.",
            queued=True,
        )

    def apply(self, target: str, payload: WireGuardPeerAction) -> WireGuardActionResult:
        # Only opaque RouterOS IDs can enter the fixed recovery script.
        kind, item_id, path, resource, _row = self._target(target)
        api = self.client.connect()
        if payload.action == "keepalive":
            if kind != "peer":
                raise ServiceError(
                    status.HTTP_409_CONFLICT,
                    "BTH manages keepalive.",
                    error_code="VPN_BTH_KEEPALIVE",
                )
            resource.set(id=item_id, **{"persistent-keepalive": f"{payload.keepalive_seconds}s"})
            return WireGuardActionResult(message="Router peer keepalive updated.")
        if payload.action == "allow_lan":
            if kind != "bth":
                raise ServiceError(status.HTTP_409_CONFLICT, "Only BTH users have this setting.")
            resource.set(id=item_id, **{"allow-lan": "yes" if payload.allow_lan else "no"})
            return WireGuardActionResult(message="Back to Home LAN access updated.")
        if payload.action != "reset":
            resource.set(id=item_id, disabled="yes" if payload.action == "disable" else "no")
            return WireGuardActionResult(message=f"Peer {payload.action}d.")
        # Run both steps locally. A separate server-side enable request could be
        # stranded if disabling this peer interrupts the server's management VPN.
        # The API call queues a background script; it does not verify a handshake.
        script = (
            f":delay 2s; {path}/set {item_id} disabled=yes; "
            f":delay 1s; {path}/set {item_id} disabled=no;"
        )
        api.get_resource("/").call("execute", {"script": script})
        return WireGuardActionResult(
            message="Reset queued on the router. Wait a few seconds, reconnect your "
            "WireGuard client, and refresh to check the handshake.",
            queued=True,
        )
