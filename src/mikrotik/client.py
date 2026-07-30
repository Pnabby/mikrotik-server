from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from routeros_api import RouterOsApiPool
from routeros_api.api import RouterOsApi
from routeros_api.exceptions import RouterOsApiError

from mikrotik.routers import RouterDefinition


_ACTIVE_CLASS_DEVICE_TYPE_PATTERNS = (
    ("Phone", re.compile(r"\bandroid\b")),
    ("PC", re.compile(r"\b(?:msft|microsoft)\b")),
    ("Chromebook", re.compile(r"\bchrome\s*os\b")),
    ("Linux device", re.compile(r"\blinux\b")),
)

_HOSTNAME_DEVICE_TYPE_PATTERNS = (
    (
        "Tablet",
        re.compile(
            r"\b(?:ipad|tablet|galaxy\s+tab|kindle|fire\s+hd|surface\s+(?:go|pro))\b"
        ),
    ),
    ("Chromebook", re.compile(r"\b(?:chrome\s*os|chromebook)\b")),
    (
        "PC",
        re.compile(
            r"\b(?:desktop|laptop|computer|workstation|pc|macbook|imac|mac\s+mini|"
            r"thinkpad|windows|surface|galaxy\s+book|win\d{0,2})\b"
        ),
    ),
    (
        "Phone",
        re.compile(
            r"\b(?:iphone|android|phone|smartphone|pixel|galaxy|oneplus|redmi|xiaomi|"
            r"oppo|vivo|realme|huawei|honor|motorola|moto|nokia|infinix|tecno|itel)\b"
        ),
    ),
)


@dataclass(slots=True)
class MikroTikConfig:
    host: str
    username: str = field(repr=False)
    password: str = field(repr=False)
    port: int | None = None
    plaintext_login: bool = False
    use_ssl: bool = False
    ssl_verify: bool = True
    ssl_verify_hostname: bool = True

    @classmethod
    def from_env(cls, router: RouterDefinition) -> "MikroTikConfig":
        load_dotenv()
        username = os.getenv("MIKROTIK_USERNAME")
        password = os.getenv("MIKROTIK_PASSWORD")

        if not username or password is None:
            raise ValueError(
                "Set MIKROTIK_USERNAME and MIKROTIK_PASSWORD before connecting."
            )

        return cls(
            host=router.host,
            username=username,
            password=password,
            port=router.port,
            plaintext_login=_env_flag("MIKROTIK_PLAINTEXT_LOGIN", default=False),
            use_ssl=_env_flag("MIKROTIK_USE_SSL", default=False),
            ssl_verify=_env_flag("MIKROTIK_SSL_VERIFY", default=True),
            ssl_verify_hostname=_env_flag("MIKROTIK_SSL_VERIFY_HOSTNAME", default=True),
        )


class MikroTikClient:
    def __init__(self, config: MikroTikConfig) -> None:
        self.config = config
        self._pool: RouterOsApiPool | None = None
        self._api: RouterOsApi | None = None
        self._dhcp_lease_hints_by_mac: dict[str, dict[str, str]] | None = None

    def connect(self) -> RouterOsApi:
        if self._api is not None:
            return self._api

        self._pool = RouterOsApiPool(
            host=self.config.host,
            username=self.config.username,
            password=self.config.password,
            port=self.config.port,
            plaintext_login=self.config.plaintext_login,
            use_ssl=self.config.use_ssl,
            ssl_verify=self.config.ssl_verify,
            ssl_verify_hostname=self.config.ssl_verify_hostname,
        )
        self._api = self._pool.get_api()
        return self._api

    def disconnect(self) -> None:
        if self._pool is not None:
            self._pool.disconnect()
        self._pool = None
        self._api = None
        self._dhcp_lease_hints_by_mac = None

    def get_system_identity(self) -> list[dict[str, str]]:
        api = self.connect()
        return api.get_resource("/system/identity").get()

    def get_interfaces(self) -> list[dict[str, str]]:
        api = self.connect()
        return api.get_resource("/interface").get()

    def get_hotspot_user(self, username: str) -> dict[str, str] | None:
        api = self.connect()
        normalized_username = _normalize_routeros_name(username)
        if not normalized_username:
            return None

        users = api.get_resource("/ip/hotspot/user").get(name=normalized_username)
        if not users:
            users = api.get_resource("/ip/hotspot/user").get()
            normalized_lookup = normalized_username.casefold()
            for user in users:
                if _normalize_routeros_name(user.get("name")).casefold() == normalized_lookup:
                    return user

            return None

        return users[0]

    def get_hotspot_active_devices(self, username: str) -> list[dict[str, str]]:
        api = self.connect()
        active_devices = api.get_resource("/ip/hotspot/active").get(user=username)
        hotspot_user = self.get_hotspot_user(username)
        user_comment = hotspot_user.get("comment", "") if hotspot_user else ""
        dhcp_lease_hints_by_mac = (
            self._get_dhcp_lease_hints_by_mac(api) if active_devices else {}
        )

        enriched_devices: list[dict[str, str]] = []
        for device in active_devices:
            enriched_device = dict(device)
            lease_hints = dhcp_lease_hints_by_mac.get(
                _normalize_mac_address(device.get("mac-address")),
                {},
            )
            if user_comment:
                enriched_device["user-comment"] = user_comment
            enriched_device["device-name"] = (
                lease_hints.get("host-name")
                or device.get("host-name")
                or device.get("host")
                or device.get("device-name")
                or "unknown"
            )
            active_class_id = lease_hints.get("class-id") or _normalize_dhcp_class_id(
                device.get("active-class-id") or device.get("class-id")
            )
            if active_class_id:
                enriched_device["class-id"] = active_class_id
            enriched_device["device-type"] = infer_device_type(
                enriched_device["device-name"],
                device.get("platform"),
                device.get("os"),
                device.get("user-agent"),
                active_class_id=active_class_id,
            )
            enriched_device["bytes-in"] = str(_parse_routeros_int(device.get("bytes-in")))
            enriched_device["bytes-out"] = str(_parse_routeros_int(device.get("bytes-out")))
            enriched_device["bytes-total"] = str(
                _parse_routeros_int(enriched_device.get("bytes-in"))
                + _parse_routeros_int(enriched_device.get("bytes-out"))
            )
            enriched_devices.append(enriched_device)

        return enriched_devices

    def get_hotspot_active_device_count(self, username: str) -> int:
        return len(self.get_hotspot_active_devices(username))

    def remove_hotspot_active_device(
        self,
        username: str,
        session_id: str,
        *,
        mac_address: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        api = self.connect()
        active_resource = api.get_resource("/ip/hotspot/active")

        target_session = self._find_hotspot_active_session(
            active_resource,
            username,
            session_id,
            mac_address=mac_address,
            ip_address=ip_address,
        )
        if target_session is None:
            return False

        target_session_id = target_session.get("id")
        if not target_session_id:
            return False

        active_resource.remove(id=target_session_id)
        return True

    def get_hotspot_total_bytes_used(self, username: str) -> int:
        hotspot_user = self.get_hotspot_user(username)
        user_bytes_in = _parse_routeros_int(hotspot_user.get("bytes-in") if hotspot_user else None)
        user_bytes_out = _parse_routeros_int(
            hotspot_user.get("bytes-out") if hotspot_user else None
        )
        total = user_bytes_in + user_bytes_out

        for device in self.get_hotspot_active_devices(username):
            total += _parse_routeros_int(device.get("bytes-in"))
            total += _parse_routeros_int(device.get("bytes-out"))

        return total

    def get_hotspot_user_usage(self, username: str) -> dict[str, int | str | None]:
        hotspot_user = self.get_hotspot_user(username)
        active_devices = self.get_hotspot_active_devices(username)

        user_bytes_in = _parse_routeros_int(hotspot_user.get("bytes-in") if hotspot_user else None)
        user_bytes_out = _parse_routeros_int(
            hotspot_user.get("bytes-out") if hotspot_user else None
        )
        active_bytes_in = sum(_parse_routeros_int(device.get("bytes-in")) for device in active_devices)
        active_bytes_out = sum(
            _parse_routeros_int(device.get("bytes-out")) for device in active_devices
        )

        limit_bytes_in = _parse_routeros_optional_int(
            hotspot_user.get("limit-bytes-in") if hotspot_user else None
        )
        limit_bytes_out = _parse_routeros_optional_int(
            hotspot_user.get("limit-bytes-out") if hotspot_user else None
        )
        limit_bytes_total = _parse_routeros_optional_int(
            hotspot_user.get("limit-bytes-total") if hotspot_user else None
        )

        return {
            "username": username,
            "user_comment": hotspot_user.get("comment") if hotspot_user else None,
            "user_bytes_in": user_bytes_in,
            "user_bytes_out": user_bytes_out,
            "user_bytes_total": user_bytes_in + user_bytes_out,
            "active_bytes_in": active_bytes_in,
            "active_bytes_out": active_bytes_out,
            "active_bytes_total": active_bytes_in + active_bytes_out,
            "combined_bytes_in": user_bytes_in + active_bytes_in,
            "combined_bytes_out": user_bytes_out + active_bytes_out,
            "combined_bytes_total": self.get_hotspot_total_bytes_used(username),
            "limit_bytes_in": limit_bytes_in,
            "limit_bytes_out": limit_bytes_out,
            "limit_bytes_total": limit_bytes_total,
        }

    def __enter__(self) -> "MikroTikClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    def _find_hotspot_active_session(
        self,
        active_resource,
        username: str,
        session_id: str,
        *,
        mac_address: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, str] | None:
        normalized_username = _normalize_routeros_name(username)
        if session_id:
            sessions = active_resource.get(id=session_id)
            for session in sessions:
                if _normalize_routeros_name(session.get("user")) == normalized_username:
                    return session

        user_sessions = active_resource.get(user=normalized_username)
        for session in user_sessions:
            if mac_address and session.get("mac-address") == mac_address:
                return session
            if ip_address and session.get("address") == ip_address:
                return session

        return None

    def _get_dhcp_lease_hints_by_mac(
        self,
        api: RouterOsApi,
    ) -> dict[str, dict[str, str]]:
        if self._dhcp_lease_hints_by_mac is not None:
            return self._dhcp_lease_hints_by_mac

        try:
            leases = api.get_resource("/ip/dhcp-server/lease").get()
        except RouterOsApiError:
            self._dhcp_lease_hints_by_mac = {}
            return self._dhcp_lease_hints_by_mac

        lease_hints_by_mac: dict[str, dict[str, str]] = {}
        for lease in leases:
            mac_addresses = {
                normalized_mac
                for key in ("mac-address", "active-mac-address")
                if (normalized_mac := _normalize_mac_address(lease.get(key)))
            }
            if not mac_addresses:
                continue

            hostname = _normalize_routeros_name(lease.get("host-name"))
            active_class_id = _normalize_dhcp_class_id(
                lease.get("active-class-id") or lease.get("class-id")
            )
            lease_hints = {}
            if hostname:
                lease_hints["host-name"] = hostname
            if active_class_id:
                lease_hints["class-id"] = active_class_id
            if lease_hints:
                for mac_address in mac_addresses:
                    lease_hints_by_mac[mac_address] = lease_hints

        self._dhcp_lease_hints_by_mac = lease_hints_by_mac
        return self._dhcp_lease_hints_by_mac


def _env_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_routeros_int(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_routeros_optional_int(value: str | None) -> int | None:
    parsed = _parse_routeros_int(value)
    return parsed or None


def _normalize_routeros_name(value: object) -> str:
    if not isinstance(value, str):
        return ""

    return value.strip()


def _normalize_mac_address(value: object) -> str:
    if not isinstance(value, str):
        return ""

    normalized = value.strip().casefold().replace(":", "").replace("-", "").replace(".", "")
    if len(normalized) != 12 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        return ""

    return normalized


def infer_device_type(
    *fallback_hints: object,
    active_class_id: object = None,
) -> str:
    """Infer a broad device type, preferring the DHCP active class ID."""

    normalized_class_id = _normalize_device_hint(active_class_id)
    for device_type, pattern in _ACTIVE_CLASS_DEVICE_TYPE_PATTERNS:
        if pattern.search(normalized_class_id):
            return device_type

    searchable_text = " ".join(
        normalized_hint
        for hint in fallback_hints
        if (normalized_hint := _normalize_device_hint(hint))
    )
    for device_type, pattern in _HOSTNAME_DEVICE_TYPE_PATTERNS:
        if pattern.search(searchable_text):
            return device_type

    return "Unknown"


def _normalize_device_hint(hint: object) -> str:
    if not isinstance(hint, str):
        return ""

    return re.sub(r"[^a-z0-9]+", " ", hint.casefold()).strip()


def _normalize_dhcp_class_id(value: object) -> str:
    return _normalize_routeros_name(value).replace("\x00", "").strip()


def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())
