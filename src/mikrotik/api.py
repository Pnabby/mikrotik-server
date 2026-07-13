from __future__ import annotations

from calendar import monthrange
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
import hmac
import os

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from mikrotik.client import MikroTikClient, MikroTikConfig, load_dotenv
from mikrotik.pages import router as pages_router


LOGIN_COMMENT_PREFIX = "login="
LOGIN_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _cors_origins() -> list[str]:
    load_dotenv()
    raw_value = os.getenv("API_CORS_ORIGINS", "*")
    origins = [item.strip() for item in raw_value.split(",") if item.strip()]
    return origins or ["*"]


app = FastAPI(title="MikroTik Hotspot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(pages_router)


class DeviceSession(BaseModel):
    session_id: str
    device_name: str
    mac_address: str | None = None
    ip_address: str | None = None
    login_by: str | None = None
    uptime: str | None = None
    server: str | None = None
    bytes_in: int
    bytes_out: int
    bytes_total: int


class HotspotStatusResponse(BaseModel):
    username: str
    profile: str | None = None
    disabled: bool
    logged_in_date: str | None = None
    expiry_date: str | None = None
    total_data_used_bytes: int
    total_data_used: str
    total_data_left_bytes: int | None = None
    total_data_left: str
    data_limit_bytes: int | None = None
    connected_devices_count: int
    connected_devices: list[DeviceSession]


class HotspotLookupRequest(BaseModel):
    username: str
    password: str


class DeviceLogoutResponse(BaseModel):
    username: str
    session_id: str
    removed: bool
    detail: str


@contextmanager
def _client_context() -> Generator[MikroTikClient, None, None]:
    try:
        config = MikroTikConfig.from_env()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    client = MikroTikClient(config)
    try:
        yield client
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Router communication failed: {exc}",
        ) from exc
    finally:
        client.disconnect()


def get_client() -> Generator[MikroTikClient, None, None]:
    with _client_context() as client:
        yield client


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hotspot/users/{username}/status", response_model=HotspotStatusResponse)
def get_hotspot_status(
    username: str,
    client: MikroTikClient = Depends(get_client),
) -> HotspotStatusResponse:
    normalized_username = username.strip()
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required.",
        )

    hotspot_user = client.get_hotspot_user(normalized_username)
    if hotspot_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hotspot user '{normalized_username}' was not found.",
        )

    return _build_hotspot_status(client, hotspot_user, normalized_username)


@app.post("/api/hotspot/user-lookup", response_model=HotspotStatusResponse)
def lookup_hotspot_user(
    credentials: HotspotLookupRequest,
    client: MikroTikClient = Depends(get_client),
) -> HotspotStatusResponse:
    normalized_username = credentials.username.strip()
    if not normalized_username or not credentials.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required.",
        )

    hotspot_user = client.get_hotspot_user(normalized_username)
    stored_password = hotspot_user.get("password") if hotspot_user is not None else None
    comparable_password = stored_password if isinstance(stored_password, str) else ""
    password_matches = hmac.compare_digest(
        comparable_password.encode("utf-8"),
        credentials.password.encode("utf-8"),
    )
    if hotspot_user is None or not password_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    return _build_hotspot_status(client, hotspot_user, normalized_username)


def _build_hotspot_status(
    client: MikroTikClient,
    hotspot_user: dict[str, str],
    fallback_username: str,
) -> HotspotStatusResponse:
    resolved_username = _resolve_hotspot_username(hotspot_user, fallback_username)
    usage = client.get_hotspot_user_usage(resolved_username)
    devices = client.get_hotspot_active_devices(resolved_username)
    data_limit_bytes = _resolve_total_data_limit(usage)
    total_data_used_bytes = int(usage["combined_bytes_total"])
    total_data_left_bytes = (
        None if data_limit_bytes is None else max(data_limit_bytes - total_data_used_bytes, 0)
    )
    logged_in_date = _resolve_logged_in_date(hotspot_user.get("comment"))

    return HotspotStatusResponse(
        username=resolved_username,
        profile=hotspot_user.get("profile"),
        disabled=_parse_bool(hotspot_user.get("disabled")),
        logged_in_date=logged_in_date,
        expiry_date=_resolve_expiry_date(hotspot_user.get("profile"), hotspot_user.get("comment")),
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


@app.post(
    "/api/hotspot/users/{username}/devices/{session_id}/logout",
    response_model=DeviceLogoutResponse,
)
def logout_hotspot_device(
    username: str,
    session_id: str,
    mac_address: str | None = None,
    ip_address: str | None = None,
    client: MikroTikClient = Depends(get_client),
) -> DeviceLogoutResponse:
    normalized_username = username.strip()
    normalized_session_id = session_id.strip()
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is required.",
        )
    if not normalized_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session ID is required.",
        )

    hotspot_user = client.get_hotspot_user(normalized_username)
    if hotspot_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hotspot user '{normalized_username}' was not found.",
        )

    resolved_username = _resolve_hotspot_username(hotspot_user, normalized_username)
    removed = client.remove_hotspot_active_device(
        resolved_username,
        normalized_session_id,
        mac_address=_normalize_optional_text(mac_address),
        ip_address=_normalize_optional_text(ip_address),
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Active session '{normalized_session_id}' was not found for user "
                f"'{normalized_username}'."
            ),
        )

    return DeviceLogoutResponse(
        username=resolved_username,
        session_id=normalized_session_id,
        removed=True,
        detail="Device session logged out successfully.",
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
    resolved_username = _normalize_optional_text(hotspot_user.get("name"))
    return resolved_username or fallback_username


def _resolve_logged_in_date(comment: object) -> str | None:
    login_datetime = _parse_login_datetime(comment)
    if login_datetime is not None:
        return _format_datetime(login_datetime)

    return _normalize_optional_text(comment)


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
        if normalized_profile == expiry_profile or normalized_profile.startswith(f"{expiry_profile}-"):
            return expiry_profile

    return None


def _parse_login_datetime(comment: object) -> datetime | None:
    if not isinstance(comment, str):
        return None

    normalized_comment = comment.strip()
    if not normalized_comment.lower().startswith(LOGIN_COMMENT_PREFIX):
        return None

    datetime_value = normalized_comment[len(LOGIN_COMMENT_PREFIX) :].strip()
    try:
        return datetime.strptime(datetime_value, LOGIN_DATETIME_FORMAT)
    except ValueError:
        return None


def _add_one_month(value: datetime) -> datetime:
    next_month = 1 if value.month == 12 else value.month + 1
    next_year = value.year + 1 if value.month == 12 else value.year
    next_month_last_day = monthrange(next_year, next_month)[1]
    next_day = min(value.day, next_month_last_day)
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
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _format_bytes(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024

    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.2f} {unit}"


def main() -> None:
    load_dotenv()
    uvicorn.run(
        "mikrotik.api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=_env_flag("API_RELOAD"),
    )


def _env_flag(name: str) -> bool:
    value = os.getenv(name)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
