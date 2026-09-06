from fastapi import APIRouter, Depends

from app.dependencies import get_hotspot_service
from app.schemas.hotspot import (
    DeviceLogoutResponse,
    HotspotLookupRequest,
    HotspotStatusResponse,
)
from app.services.hotspot import HotspotService


router = APIRouter(prefix="/api/routers/{router_id}/hotspot", tags=["hotspot"])


@router.get("/users/{username}/status", response_model=HotspotStatusResponse)
def get_hotspot_status(
    username: str,
    service: HotspotService = Depends(get_hotspot_service),
) -> HotspotStatusResponse:
    return service.get_status(username)


@router.post("/user-lookup", response_model=HotspotStatusResponse)
def lookup_hotspot_user(
    credentials: HotspotLookupRequest,
    service: HotspotService = Depends(get_hotspot_service),
) -> HotspotStatusResponse:
    return service.lookup(credentials.username, credentials.password.get_secret_value())


@router.post(
    "/users/{username}/devices/{session_id}/logout",
    response_model=DeviceLogoutResponse,
)
def logout_hotspot_device(
    username: str,
    session_id: str,
    mac_address: str | None = None,
    ip_address: str | None = None,
    service: HotspotService = Depends(get_hotspot_service),
) -> DeviceLogoutResponse:
    return service.logout_device(
        username,
        session_id,
        mac_address=mac_address,
        ip_address=ip_address,
    )
