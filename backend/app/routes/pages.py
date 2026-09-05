from __future__ import annotations

from typing import Annotated
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.integrations.mikrotik.registry import (
    DEFAULT_ROUTER_ID,
    RouterDefinition,
    UnknownRouterError,
    get_router,
    iter_routers,
)
from app.schemas.routers import RouterSummary
from app.schemas.status_session import StatusSessionResponse

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_db_session)]
STATUS_COOKIE_NAME = "flint_status_user"
STATUS_DEVICE_IP_COOKIE_NAME = "flint_status_device_ip"
STATUS_DEVICE_MAC_COOKIE_NAME = "flint_status_device_mac"
STATUS_ROUTER_COOKIE_NAME = "flint_status_router"
STATUS_COOKIE_MAX_AGE = 60 * 60 * 12


@router.get("/api/status-session", response_model=StatusSessionResponse, tags=["status-page"])
def status_session(request: Request, session: SessionDependency) -> StatusSessionResponse:
    selected_router = _resolve_page_router(request, session)
    return StatusSessionResponse(
        username=_resolve_page_username(request),
        current_device_ip=_resolve_current_device_ip(request),
        current_device_mac=_resolve_current_device_mac(request),
        selected_router=_router_summary(selected_router),
        routers=[_router_summary(item) for item in iter_routers(session)],
    )


@router.get("/", include_in_schema=False)
@router.get("/login", include_in_schema=False)
@router.get("/signup", include_in_schema=False)
@router.get("/account", include_in_schema=False)
@router.get("/profile", include_in_schema=False)
@router.get("/status", include_in_schema=False)
@router.get("/status/{username}", include_in_schema=False)
def hotspot_status_page(request: Request, username: str | None = None) -> Response:
    # Preserve the old SPA paths. Usernames in paths remain ignored.
    return _frontend_response(request)


@router.get("/assets/{asset_path:path}", include_in_schema=False)
def frontend_asset(asset_path: str) -> Response:
    assets_root = (get_settings().frontend_dist_dir / "assets").resolve()
    candidate = (assets_root / asset_path).resolve()
    if assets_root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return FileResponse(candidate)


@router.get("/launch-status", include_in_schema=False)
def launch_status_redirect(
    request: Request,
    session: SessionDependency,
) -> RedirectResponse:
    return _build_launch_response(
        request,
        session,
        _first_query_value(request, ("username", "user", "name", "login", "hotspot_user")),
        _first_query_value(request, ("ip", "ip_address", "address")),
        _first_query_value(request, ("mac", "mac_address", "mac-address")),
        _first_query_value(request, ("router_id", "router", "site_id", "site")),
    )


@router.post("/launch-status", include_in_schema=False)
async def launch_status_page(
    request: Request,
    session: SessionDependency,
) -> RedirectResponse:
    posted_values = _extract_posted_values(await request.body())
    return _build_launch_response(
        request,
        session,
        _first_posted_value(
            posted_values, ("username", "user", "name", "login", "hotspot_user")
        ),
        _first_posted_value(posted_values, ("ip", "ip_address", "address")),
        _first_posted_value(posted_values, ("mac", "mac_address", "mac-address")),
        _first_posted_value(
            posted_values, ("router_id", "router", "site_id", "site")
        ),
    )


def _frontend_response(request: Request) -> Response:
    index_path = get_settings().frontend_dist_dir / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    frontend_url = get_settings().frontend_url.rstrip("/") + request.url.path
    if request.query_params:
        frontend_url = f"{frontend_url}?{urlencode(list(request.query_params.multi_items()))}"
    return RedirectResponse(frontend_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def _build_launch_response(
    request: Request,
    session: Session,
    username: str | None,
    device_ip: str | None,
    device_mac: str | None,
    router_id: str | None,
) -> RedirectResponse:
    selected_router = _resolve_allowed_router(session, router_id or DEFAULT_ROUTER_ID)
    response = RedirectResponse(url="/status", status_code=status.HTTP_303_SEE_OTHER)
    if username:
        _set_status_cookie(response, request, STATUS_COOKIE_NAME, username)
        _set_status_cookie(
            response, request, STATUS_ROUTER_COOKIE_NAME, selected_router.router_id
        )
        if device_ip:
            _set_status_cookie(response, request, STATUS_DEVICE_IP_COOKIE_NAME, device_ip)
        else:
            response.delete_cookie(STATUS_DEVICE_IP_COOKIE_NAME, path="/")
        if device_mac:
            _set_status_cookie(response, request, STATUS_DEVICE_MAC_COOKIE_NAME, device_mac)
        else:
            response.delete_cookie(STATUS_DEVICE_MAC_COOKIE_NAME, path="/")
    else:
        for cookie_name in (
            STATUS_COOKIE_NAME,
            STATUS_DEVICE_IP_COOKIE_NAME,
            STATUS_DEVICE_MAC_COOKIE_NAME,
            STATUS_ROUTER_COOKIE_NAME,
        ):
            response.delete_cookie(cookie_name, path="/")
    return response


def _resolve_page_username(request: Request) -> str | None:
    return _normalize_optional_text(request.cookies.get(STATUS_COOKIE_NAME))


def _resolve_page_router(request: Request, session: Session) -> RouterDefinition:
    query_router_id = _first_query_value(
        request, ("router_id", "router", "site_id", "site")
    )
    if query_router_id:
        return _resolve_allowed_router(session, query_router_id)
    router_id = _normalize_optional_text(request.cookies.get(STATUS_ROUTER_COOKIE_NAME))
    try:
        return get_router(session, router_id or DEFAULT_ROUTER_ID)
    except UnknownRouterError:
        return get_router(session, DEFAULT_ROUTER_ID)


def _resolve_allowed_router(session: Session, router_id: str) -> RouterDefinition:
    try:
        return get_router(session, router_id)
    except UnknownRouterError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Router is not configured.",
        ) from exc


def _resolve_current_device_ip(request: Request) -> str | None:
    query_ip = _first_query_value(request, ("ip", "ip_address", "address"))
    if query_ip:
        return query_ip
    cookie_ip = _normalize_optional_text(request.cookies.get(STATUS_DEVICE_IP_COOKIE_NAME))
    if cookie_ip:
        return cookie_ip
    for header_name in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        header_value = _normalize_optional_text(request.headers.get(header_name))
        if header_value:
            return header_value.split(",", 1)[0].strip()
    return _normalize_optional_text(request.client.host) if request.client else None


def _resolve_current_device_mac(request: Request) -> str | None:
    return _first_query_value(request, ("mac", "mac_address", "mac-address")) or (
        _normalize_optional_text(request.cookies.get(STATUS_DEVICE_MAC_COOKIE_NAME))
    )


def _first_query_value(request: Request, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _normalize_optional_text(request.query_params.get(key))
        if value:
            return value
    return None


def _extract_posted_values(body: bytes) -> dict[str, list[str]]:
    try:
        return parse_qs(body.decode("utf-8"), keep_blank_values=False)
    except UnicodeDecodeError:
        return {}


def _first_posted_value(
    posted_values: dict[str, list[str]], keys: tuple[str, ...]
) -> str | None:
    for key in keys:
        values = posted_values.get(key)
        if values:
            normalized_value = _normalize_optional_text(values[0])
            if normalized_value:
                return normalized_value
    return None


def _set_status_cookie(
    response: RedirectResponse, request: Request, name: str, value: str
) -> None:
    response.set_cookie(
        name,
        value,
        max_age=STATUS_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _router_summary(router_definition: RouterDefinition) -> RouterSummary:
    return RouterSummary(
        router_id=router_definition.router_id,
        name=router_definition.name,
        hotspot_network=router_definition.hotspot_network,
    )
