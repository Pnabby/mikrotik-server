from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.core.security import Argon2PinHasher
from app.db.session import get_db_session
from app.dependencies import ROUTER_UNAVAILABLE_DETAIL, mikrotik_client_context
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.integrations.paystack import paystack_is_configured
from app.models.customer import Customer
from app.routes.auth import get_authenticated_customer
from app.schemas.account import (
    ChangePinRequest,
    ChangePinResponse,
    CustomerAccountResponse,
    DeleteAccountRequest,
    DeleteAccountResponse,
    PhoneVerificationCompleteRequest,
    PhoneVerificationResponse,
    PhoneVerificationStartRequest,
    PhoneVerificationStartResponse,
)
from app.schemas.hotspot import DeviceLogoutResponse, HotspotStatusResponse
from app.services.account_deletion import AccountDeletionService
from app.services.customer_account import CustomerAccountService
from app.services.customer_auth import CUSTOMER_SESSION_COOKIE
from app.services.hotspot import HotspotService
from app.services.phone_verification import PhoneVerificationService
from app.services.pin_management import PinManagementService

router = APIRouter(prefix="/api/account", tags=["account"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
CustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.post("/phone-verification/start", response_model=PhoneVerificationStartResponse)
def start_phone_verification(
    payload: PhoneVerificationStartRequest,
    request: Request,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PhoneVerificationStartResponse:
    result = PhoneVerificationService(session, settings).start(
        customer,
        payload.phone_number,
        requested_ip=request.client.host if request.client else None,
    )
    return PhoneVerificationStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/phone-verification/complete", response_model=PhoneVerificationResponse)
def complete_phone_verification(
    payload: PhoneVerificationCompleteRequest,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> PhoneVerificationResponse:
    PhoneVerificationService(session, settings).complete(
        customer, payload.challenge_id, payload.phone_number, payload.code.get_secret_value()
    )
    return PhoneVerificationResponse()


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


CustomerHotspotServiceDependency = Annotated[HotspotService, Depends(get_customer_hotspot_service)]


@router.get("", response_model=CustomerAccountResponse)
def account_overview(
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> CustomerAccountResponse:
    return CustomerAccountService(
        session,
        payments_enabled=paystack_is_configured(settings),
    ).overview(customer)


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


@router.post("/delete", response_model=DeleteAccountResponse)
def delete_customer_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> DeleteAccountResponse:
    try:
        router_definition = get_router(session, customer.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ROUTER_UNAVAILABLE_DETAIL,
        ) from exc
    with mikrotik_client_context(router_definition) as client:
        AccountDeletionService(session).delete_with_pin(
            customer,
            payload.pin.get_secret_value(),
            Argon2PinHasher.from_settings(settings),
            client,
        )
    response.delete_cookie(
        CUSTOMER_SESSION_COOKIE,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return DeleteAccountResponse()


@router.post("/change-pin", response_model=ChangePinResponse)
def change_customer_pin(
    payload: ChangePinRequest,
    request: Request,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> ChangePinResponse:
    try:
        router_definition = get_router(session, customer.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            ROUTER_UNAVAILABLE_DETAIL,
        ) from exc
    try:
        pin_hasher = Argon2PinHasher.from_settings(settings)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PIN change is not configured.",
        ) from exc
    with mikrotik_client_context(router_definition) as client:
        PinManagementService(session, settings).change_pin(
            customer,
            payload,
            pin_hasher,
            client,
            current_session_token=request.cookies.get(CUSTOMER_SESSION_COOKIE),
            ip_address=request.client.host if request.client else None,
        )
    return ChangePinResponse()
