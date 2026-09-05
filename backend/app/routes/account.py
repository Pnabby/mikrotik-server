from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.dependencies import ROUTER_UNAVAILABLE_DETAIL, mikrotik_client_context
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.models.customer import Customer
from app.routes.auth import get_authenticated_customer
from app.schemas.account import CustomerAccountResponse
from app.schemas.hotspot import DeviceLogoutResponse, HotspotStatusResponse
from app.services.customer_account import CustomerAccountService
from app.services.hotspot import HotspotService

router = APIRouter(prefix="/api/account", tags=["account"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
CustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]


def get_customer_hotspot_service(
    customer: CustomerDependency,
    session: SessionDependency,
) -> Generator[HotspotService, None, None]:
    try:
        router_definition = get_router(session, customer.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ROUTER_UNAVAILABLE_DETAIL,
        ) from exc
    with mikrotik_client_context(router_definition) as client:
        yield HotspotService(router_definition, client)


CustomerHotspotServiceDependency = Annotated[
    HotspotService, Depends(get_customer_hotspot_service)
]


@router.get("", response_model=CustomerAccountResponse)
def account_overview(
    customer: CustomerDependency,
    session: SessionDependency,
) -> CustomerAccountResponse:
    return CustomerAccountService(session).overview(customer)


@router.get("/hotspot-status", response_model=HotspotStatusResponse)
def customer_hotspot_status(
    customer: CustomerDependency,
    hotspot_service: CustomerHotspotServiceDependency,
) -> HotspotStatusResponse:
    return hotspot_service.get_status(customer.username)


@router.post(
    "/devices/{session_id}/logout",
    response_model=DeviceLogoutResponse,
)
def logout_customer_hotspot_device(
    session_id: str,
    customer: CustomerDependency,
    hotspot_service: CustomerHotspotServiceDependency,
    mac_address: str | None = None,
    ip_address: str | None = None,
) -> DeviceLogoutResponse:
    return hotspot_service.logout_device(
        customer.username,
        session_id,
        mac_address=mac_address,
        ip_address=ip_address,
    )
