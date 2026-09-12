from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Self

from routeros_api import RouterOsApiPool
from routeros_api.api import RouterOsApi
from routeros_api.exceptions import RouterOsApiError

from app.core.config import Settings, get_settings
from app.integrations.mikrotik.registry import RouterDefinition

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

# RouterOS exposes counters and other read-only values beside the fields accepted
# by `/ip/hotspot/user/add`.  Keeping this allow-list explicit prevents a transfer
# from accidentally trying to write runtime state such as `.id`, uptime or byte
# counters while still preserving every configurable per-user setting.
_HOTSPOT_USER_TRANSFER_FIELDS = (
    "server",
    "name",
    "password",
    "address",
    "mac-address",
    "profile",
    "routes",
    "email",
    "limit-uptime",
    "limit-bytes-in",
    "limit-bytes-out",
    "limit-bytes-total",
    "comment",
    "disabled",
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
    def from_env(cls, router: RouterDefinition) -> MikroTikConfig:
        return cls.from_settings(router, get_settings())

    @classmethod
    def from_settings(cls, router: RouterDefinition, settings: Settings) -> MikroTikConfig:
        username = settings.mikrotik_username
        password = (
            settings.mikrotik_password.get_secret_value()
            if settings.mikrotik_password is not None
            else None
        )

        if not username or password is None:
            raise ValueError(
                "Set MIKROTIK_USERNAME and MIKROTIK_PASSWORD before connecting."
            )

        return cls(
            host=router.host,
            username=username,
            password=password,
            port=router.port,
            plaintext_login=settings.mikrotik_plaintext_login,
            use_ssl=settings.mikrotik_use_ssl,
            ssl_verify=settings.mikrotik_ssl_verify,
            ssl_verify_hostname=settings.mikrotik_ssl_verify_hostname,
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

    def get_dhcp_leases(self) -> list[dict[str, str]]:
        """Return DHCP leases, including RouterOS active address/MAC fields."""
        api = self.connect()
        return api.get_resource("/ip/dhcp-server/lease").get()

    def get_bridge_hosts(self) -> list[dict[str, str]]:
        """Return the bridge forwarding table used to identify physical ports."""
        api = self.connect()
        try:
            return api.get_resource("/interface/bridge/host").get()
        except RouterOsApiError:
            # Lease health remains useful when this optional table is unavailable
            # or the RouterOS API account lacks bridge-host read permission.
            return []

    def force_ip_cloud_update(self) -> None:
        """Ask RouterOS IP Cloud to refresh its DDNS/BTH address immediately."""
        api = self.connect()
        api.get_resource("/ip/cloud").call("force-update")

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

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None:
        api = self.connect()
        normalized_profile = _normalize_routeros_name(profile)
        if not normalized_profile:
            return None
        profiles = api.get_resource("/ip/hotspot/user/profile").get(name=normalized_profile)
        return profiles[0] if profiles else None

    def get_hotspot_user_profiles(self) -> list[dict[str, str]]:
        """Return every HotSpot user profile currently defined on the router."""
        api = self.connect()
        return api.get_resource("/ip/hotspot/user/profile").get()

    def create_hotspot_user(
        self,
        *,
        username: str,
        password: str,
        profile: str,
        comment: str,
        disabled: bool = True,
    ) -> None:
        api = self.connect()
        api.get_resource("/ip/hotspot/user").add(
            name=_normalize_routeros_name(username),
            password=password,
            profile=_normalize_routeros_name(profile),
            comment=comment,
            disabled="yes" if disabled else "no",
        )

    def activate_hotspot_user(
        self,
        *,
        username: str,
        profile: str,
        comment: str,
        data_limit_bytes: int | None,
    ) -> dict[str, str]:
        """Apply a paid plan to an existing HotSpot user and return read-back state."""
        hotspot_user = self.get_hotspot_user(username)
        if hotspot_user is None or not hotspot_user.get("id"):
            raise RouterOsApiError("HotSpot user is missing an id.")
        if self.get_hotspot_user_profile(profile) is None:
            raise RouterOsApiError("HotSpot profile does not exist.")

        api = self.connect()
        user_resource = api.get_resource("/ip/hotspot/user")
        # End every old-plan session before clearing counters. Otherwise RouterOS
        # may write the terminated session's usage back after the reset. Do not
        # disable an already-enabled customer during these preparatory operations:
        # if RouterOS becomes unavailable midway through, their existing plan must
        # remain usable and a later retry can safely repeat the cleanup.
        active_resource = api.get_resource("/ip/hotspot/active")
        normalized_username = _normalize_routeros_name(username)
        self._remove_hotspot_records(active_resource, normalized_username)
        cookie_resource = api.get_resource("/ip/hotspot/cookie")
        self._remove_hotspot_records(cookie_resource, normalized_username)
        user_resource.call("reset-counters", {"numbers": hotspot_user["id"]})
        # Apply the allowance, marker, and enabled state together as the final
        # operation. Replacing the comment deliberately removes any old login=
        # timestamp so the new plan starts only after the next portal login.
        user_resource.set(
            **{
                "id": hotspot_user["id"],
                "profile": _normalize_routeros_name(profile),
                "limit-bytes-total": str(data_limit_bytes or 0),
                "comment": comment,
                "disabled": "no",
            }
        )
        updated_user = self.get_hotspot_user(username)
        if updated_user is None:
            raise RouterOsApiError("HotSpot user disappeared after activation.")
        return updated_user

    def change_hotspot_user_password(self, username: str, password: str) -> None:
        """Change a HotSpot password after invalidating active and remembered logins."""
        hotspot_user = self.get_hotspot_user(username)
        if hotspot_user is None or not hotspot_user.get("id"):
            raise RouterOsApiError("HotSpot user is missing an id.")
        if not password:
            raise ValueError("A HotSpot password is required.")

        api = self.connect()
        normalized_username = _normalize_routeros_name(username)
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/active"), normalized_username
        )
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/cookie"), normalized_username
        )
        api.get_resource("/ip/hotspot/user").set(
            id=hotspot_user["id"],
            password=password,
        )

    def clear_hotspot_authentication(self, username: str) -> dict[str, str] | None:
        """End every session/cookie, then return counters after RouterOS settles them."""
        api = self.connect()
        normalized_username = _normalize_routeros_name(username)
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/active"), normalized_username
        )
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/cookie"), normalized_username
        )
        return self.get_hotspot_user(normalized_username)

    def create_hotspot_user_copy(
        self,
        user: dict[str, str],
        *,
        byte_limits: dict[str, int | None],
    ) -> dict[str, str]:
        """Create a transferred user from writable source fields and read it back."""
        username = _normalize_routeros_name(user.get("name"))
        profile = _normalize_routeros_name(user.get("profile"))
        if not username or not profile or not user.get("password"):
            raise RouterOsApiError("HotSpot user is missing transfer credentials.")
        if self.get_hotspot_user(username) is not None:
            raise RouterOsApiError("HotSpot user already exists on the destination.")
        if self.get_hotspot_user_profile(profile) is None:
            raise RouterOsApiError("HotSpot profile does not exist on the destination.")

        attributes = {
            field: str(user[field])
            for field in _HOTSPOT_USER_TRANSFER_FIELDS
            if field in user and user[field] is not None
        }
        attributes["name"] = username
        attributes["profile"] = profile
        for limit_field, remaining in byte_limits.items():
            if remaining is None:
                attributes[limit_field] = "0"
            else:
                # RouterOS treats zero as unlimited. One byte represents an
                # exhausted finite allowance without reopening unlimited access.
                attributes[limit_field] = str(max(1, remaining))

        self.connect().get_resource("/ip/hotspot/user").add(**attributes)
        copied_user = self.get_hotspot_user(username)
        if copied_user is None:
            raise RouterOsApiError("Transferred HotSpot user could not be read back.")
        return copied_user

    @staticmethod
    def _remove_hotspot_records(resource, username: str) -> None:
        """Remove sessions/cookies and tolerate RouterOS expiry races."""
        for record in resource.get(user=username):
            if record_id := record.get("id"):
                try:
                    resource.remove(id=record_id)
                except RouterOsApiError:
                    # Active sessions and their cookies can disappear together.
                    # A fresh read below distinguishes that harmless race from an
                    # actual cleanup failure.
                    pass

        if resource.get(user=username):
            raise RouterOsApiError("HotSpot authentication records could not be cleared.")

    def remove_hotspot_user(self, username: str, *, expected_comment: str) -> bool:
        hotspot_user = self.get_hotspot_user(username)
        if hotspot_user is None:
            return True
        if hotspot_user.get("comment") != expected_comment:
            return False

        hotspot_user_id = hotspot_user.get("id")
        if not hotspot_user_id:
            return False
        api = self.connect()
        api.get_resource("/ip/hotspot/user").remove(id=hotspot_user_id)
        return self.get_hotspot_user(username) is None

    def delete_hotspot_user(self, username: str) -> bool:
        """Remove a customer's RouterOS identity and every reusable login record."""
        hotspot_user = self.get_hotspot_user(username)
        if hotspot_user is None:
            return True

        hotspot_user_id = hotspot_user.get("id")
        if not hotspot_user_id:
            return False
        api = self.connect()
        normalized_username = _normalize_routeros_name(username)
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/active"), normalized_username
        )
        self._remove_hotspot_records(
            api.get_resource("/ip/hotspot/cookie"), normalized_username
        )
        api.get_resource("/ip/hotspot/user").remove(id=hotspot_user_id)
        return self.get_hotspot_user(username) is None

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

    def get_hotspot_active_sessions(self) -> list[dict[str, str]]:
        """Return all live HotSpot sessions for administrative monitoring."""
        api = self.connect()
        return [dict(session) for session in api.get_resource("/ip/hotspot/active").get()]

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

        # Clear only this device's saved HotSpot login before ending its active
        # session. Doing this first ensures a cookie-cleanup failure does not leave
        # the UI reporting a completed logout while the device can still auto-login.
        target_mac_address = _normalize_mac_address(
            target_session.get("mac-address") or mac_address
        )
        if target_mac_address:
            self._remove_hotspot_device_cookie(
                api.get_resource("/ip/hotspot/cookie"),
                _normalize_routeros_name(username),
                target_mac_address,
            )
        active_resource.remove(id=target_session_id)
        return True

    @staticmethod
    def _remove_hotspot_device_cookie(
        cookie_resource,
        username: str,
        mac_address: str,
    ) -> None:
        def matching_cookies() -> list[dict[str, str]]:
            return [
                cookie
                for cookie in cookie_resource.get(user=username)
                if _normalize_mac_address(cookie.get("mac-address")) == mac_address
            ]

        for hotspot_cookie in matching_cookies():
            if cookie_id := hotspot_cookie.get("id"):
                try:
                    cookie_resource.remove(id=cookie_id)
                except RouterOsApiError:
                    # RouterOS may expire a cookie between the read and remove.
                    # The verification below treats that race as success.
                    pass

        if matching_cookies():
            raise RouterOsApiError("The device HotSpot cookie could not be cleared.")

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

    def __enter__(self) -> Self:
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
