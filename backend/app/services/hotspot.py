from __future__ import annotations

import hmac
from calendar import monthrange
from datetime import UTC, datetime, timedelta

from fastapi import status

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.client import MikroTikClient, infer_device_type
from app.integrations.mikrotik.registry import RouterDefinition
from app.schemas.hotspot import DeviceLogoutResponse, DeviceSession, HotspotStatusResponse

LOGIN_COMMENT_PREFIX = "login="
LOGIN_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class HotspotService:
    def __init__(self, router: RouterDefinition, client: MikroTikClient) -> None:
        self.router = router
        self.client = client

    def get_status(self, username: str) -> HotspotStatusResponse:
        normalized_username = username.strip()
        if not normalized_username:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Username is required.")

        hotspot_user = self.client.get_hotspot_user(normalized_username)
        if hotspot_user is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Hotspot user was not found.")

        return self._build_status(hotspot_user, normalized_username)

    def lookup(self, username: str, password: str) -> HotspotStatusResponse:
        normalized_username = username.strip()
        if not normalized_username or not password:
            raise ServiceError(
                status.HTTP_400_BAD_REQUEST,
                "Username and password are required.",
            )

        hotspot_user = self.client.get_hotspot_user(normalized_username)
        stored_password = hotspot_user.get("password") if hotspot_user is not None else None
        comparable_password = stored_password if isinstance(stored_password, str) else ""
        password_matches = hmac.compare_digest(
            comparable_password.encode("utf-8"),
            password.encode("utf-8"),
        )
        if hotspot_user is None or not password_matches:
            raise ServiceError(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid username or password.",
            )

        return self._build_status(hotspot_user, normalized_username)

    def logout_device(
        self,
        username: str,
        session_id: str,
        *,
        mac_address: str | None = None,
        ip_address: str | None = None,
    ) -> DeviceLogoutResponse:
        normalized_username = username.strip()
        normalized_session_id = session_id.strip()
        if not normalized_username:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Username is required.")
        if not normalized_session_id:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Session ID is required.")

        hotspot_user = self.client.get_hotspot_user(normalized_username)
        if hotspot_user is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Hotspot user was not found.")

        resolved_username = _resolve_hotspot_username(hotspot_user, normalized_username)
        removed = self.client.remove_hotspot_active_device(
            resolved_username,
            normalized_session_id,
            mac_address=_normalize_optional_text(mac_address),
            ip_address=_normalize_optional_text(ip_address),
        )
        if not removed:
            raise ServiceError(
                status.HTTP_404_NOT_FOUND,
                "Active session was not found for this user.",
            )

        return DeviceLogoutResponse(
            router_id=self.router.router_id,
            router_name=self.router.name,
            username=resolved_username,
            session_id=normalized_session_id,
            removed=True,
            detail="Device session and saved login removed successfully.",
        )

    def _build_status(
        self,
        hotspot_user: dict[str, str],
        fallback_username: str,
    ) -> HotspotStatusResponse:
        resolved_username = _resolve_hotspot_username(hotspot_user, fallback_username)
        usage = self.client.get_hotspot_user_usage(resolved_username)
        devices = self.client.get_hotspot_active_devices(resolved_username)
        data_limit_bytes = _resolve_total_data_limit(usage)
        total_data_used_bytes = int(usage["combined_bytes_total"])
        total_data_left_bytes = (
            None
            if data_limit_bytes is None
            else max(data_limit_bytes - total_data_used_bytes, 0)
        )

        return HotspotStatusResponse(
            router_id=self.router.router_id,
            router_name=self.router.name,
            username=resolved_username,
            profile=hotspot_user.get("profile"),
            disabled=_parse_bool(hotspot_user.get("disabled")),
            logged_in_date=_resolve_logged_in_date(hotspot_user.get("comment")),
            expiry_date=_resolve_expiry_date(
                hotspot_user.get("profile"), hotspot_user.get("comment")
            ),
            total_data_used_bytes=total_data_used_bytes,
            total_data_used=_format_bytes(total_data_used_bytes),
            total_data_left_bytes=total_data_left_bytes,
            total_data_left=(
                "Unlimited"
                if total_data_left_bytes is None
                else _format_bytes(total_data_left_bytes)
            ),
            data_limit_bytes=data_limit_bytes,
            connected_devices_count=len(devices),
            connected_devices=[
                DeviceSession(
                    session_id=device.get("id", ""),
                    device_name=device.get("device-name", "unknown"),
                    device_type=device.get("device-type")
                    or infer_device_type(
                        device.get("device-name"),
                        device.get("platform"),
                        device.get("os"),
                        device.get("user-agent"),
                        active_class_id=device.get("active-class-id")
                        or device.get("class-id"),
                    ),
                    mac_address=device.get("mac-address"),
                    ip_address=device.get("address"),
                    login_by=device.get("login-by"),
                    uptime=device.get("uptime"),
                    server=device.get("server"),
                    bytes_in=_parse_int(device.get("bytes-in")),
                    bytes_out=_parse_int(device.get("bytes-out")),
                    bytes_total=_parse_int(device.get("bytes-total")),
                )
                for device in devices
            ],
        )


def _resolve_total_data_limit(usage: dict[str, int | str | None]) -> int | None:
    limit_total = usage.get("limit_bytes_total")
    if isinstance(limit_total, int):
        return limit_total

    limit_in = usage.get("limit_bytes_in")
    limit_out = usage.get("limit_bytes_out")
    if isinstance(limit_in, int) and isinstance(limit_out, int):
        return limit_in + limit_out
    return None


def _resolve_hotspot_username(hotspot_user: dict[str, str], fallback_username: str) -> str:
    return _normalize_optional_text(hotspot_user.get("name")) or fallback_username


def _resolve_logged_in_date(comment: object) -> str | None:
    login_datetime = _parse_login_datetime(comment)
    return _format_datetime(login_datetime) if login_datetime else None


def _resolve_expiry_date(profile: object, comment: object) -> str | None:
    login_datetime = _parse_login_datetime(comment)
    if login_datetime is None:
        return None
    expiry_profile = _resolve_expiry_profile(profile)
    if expiry_profile == "daily":
        return _format_datetime(login_datetime + timedelta(days=1))
    if expiry_profile == "weekly":
        return _format_datetime(login_datetime + timedelta(weeks=1))
    if expiry_profile == "monthly":
        return _format_datetime(_add_one_month(login_datetime))
    return None


def _resolve_expiry_profile(profile: object) -> str | None:
    if not isinstance(profile, str):
        return None
    normalized_profile = profile.strip().lower()
    for expiry_profile in ("daily", "weekly", "monthly"):
        if normalized_profile == expiry_profile or normalized_profile.startswith(
            f"{expiry_profile}-"
        ):
            return expiry_profile
    return None


def _parse_login_datetime(comment: object) -> datetime | None:
    if not isinstance(comment, str):
        return None
    for component in comment.strip().split(";"):
        key, separator, value = component.partition("=")
        if not separator or key.strip().casefold() != LOGIN_COMMENT_PREFIX.rstrip("="):
            continue
        try:
            return datetime.strptime(value.strip(), LOGIN_DATETIME_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _add_one_month(value: datetime) -> datetime:
    next_month = 1 if value.month == 12 else value.month + 1
    next_year = value.year + 1 if value.month == 12 else value.year
    next_day = min(value.day, monthrange(next_year, next_month)[1])
    return value.replace(year=next_year, month=next_month, day=next_day)


def _format_datetime(value: datetime) -> str:
    return value.strftime(LOGIN_DATETIME_FORMAT)


def _parse_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    return f"{int(value)} {unit}" if unit == "B" else f"{value:.2f} {unit}"
