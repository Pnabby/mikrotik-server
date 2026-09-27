from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.core.security import Argon2PinHasher
from app.db.session import get_db_session
from app.integrations.brevo.client import (
    BrevoEmailSender,
    EmailDeliveryError,
    OtpEmailSender,
)
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import get_router
from app.integrations.mnotify import MNotifySmsSender, SmsDeliveryError, SmsSender
from app.models.customer import Customer
from app.schemas.account import (
    AccountUnlockCompleteRequest,
    AccountUnlockResponse,
    AccountUnlockStartRequest,
    AuthenticatedCustomerResponse,
    ChangePinResponse,
    CustomerLoginRequest,
    LogoutResponse,
    PinResetCompleteRequest,
    PinResetSmsRequest,
    PinResetStartRequest,
    PinResetStartResponse,
    UsernameRecoveryCompleteRequest,
    UsernameRecoveryResponse,
)
from app.services.customer_auth import (
    CUSTOMER_SESSION_COOKIE,
    CustomerAuthenticationService,
)
from app.services.pin_management import PasswordRouterClient, PinManagementService

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
PasswordRouterFactory = Callable[[str], PasswordRouterClient]


def get_password_email_sender(settings: SettingsDependency) -> OtpEmailSender:
    try:
        return BrevoEmailSender.from_settings(settings)
    except EmailDeliveryError:
        return _UnavailablePasswordEmailSender()


class _UnavailablePasswordEmailSender:
    def send_registration_otp(self, *, recipient: str, code: str, expires_in_minutes: int) -> None:
        raise EmailDeliveryError("Transactional email is not configured.")

    def send_pin_reset_otp(self, *, recipient: str, code: str, expires_in_minutes: int) -> None:
        raise EmailDeliveryError("Transactional email is not configured.")

    def send_username_recovery_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Transactional email is not configured.")

    def send_account_unlock_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Transactional email is not configured.")


PasswordEmailSenderDependency = Annotated[OtpEmailSender, Depends(get_password_email_sender)]


def get_password_sms_sender(settings: SettingsDependency) -> SmsSender:
    try:
        return MNotifySmsSender.from_settings(settings)
    except SmsDeliveryError:
        return _UnavailablePasswordSmsSender()


class _UnavailablePasswordSmsSender:
    def send(self, *, recipient: str, message: str) -> None:
        raise SmsDeliveryError("SMS delivery is not configured.")

    def send_verification_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise SmsDeliveryError("SMS delivery is not configured.")

    def send_pin_reset_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise SmsDeliveryError("SMS delivery is not configured.")


PasswordSmsSenderDependency = Annotated[SmsSender, Depends(get_password_sms_sender)]


def get_password_router_factory(
    settings: SettingsDependency,
    session: SessionDependency,
) -> PasswordRouterFactory:
    def create_client(router_id: str) -> MikroTikClient:
        return MikroTikClient(
            MikroTikConfig.from_settings(get_router(session, router_id), settings)
        )

    return create_client


PasswordRouterFactoryDependency = Annotated[
    PasswordRouterFactory, Depends(get_password_router_factory)
]


def get_authenticated_customer(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Customer:
    return CustomerAuthenticationService(session, settings).authenticate(
        request.cookies.get(CUSTOMER_SESSION_COOKIE)
    )


AuthenticatedCustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]


@router.post("/login", response_model=AuthenticatedCustomerResponse)
def login(
    payload: CustomerLoginRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthenticatedCustomerResponse:
    result = CustomerAuthenticationService(session, settings).login(
        payload,
        Argon2PinHasher.from_settings(settings),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    cookie_options = {
        "httponly": True,
        "secure": request.url.scheme == "https",
        "samesite": "lax",
        "path": "/",
    }
    if result.persistent:
        cookie_options.update(
            max_age=settings.remembered_customer_session_ttl_seconds,
            expires=result.expires_at,
        )
    response.set_cookie(CUSTOMER_SESSION_COOKIE, result.token, **cookie_options)
    return AuthenticatedCustomerResponse(
        username=result.customer.username,
        redirect_to=(
            "/account" if result.customer.phone_verified_at is not None else "/verify-phone"
        ),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> LogoutResponse:
    CustomerAuthenticationService(session, settings).logout(
        request.cookies.get(CUSTOMER_SESSION_COOKIE)
    )
    response.delete_cookie(CUSTOMER_SESSION_COOKIE, path="/")
    return LogoutResponse()


@router.post("/pin-reset/start", response_model=PinResetStartResponse)
def start_pin_reset(
    payload: PinResetStartRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    sender: PasswordEmailSenderDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> PinResetStartResponse:
    result = PinManagementService(session, settings).start_reset(
        payload,
        sender,
        router_factory,
        requested_ip=request.client.host if request.client else None,
    )
    return PinResetStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/pin-reset/sms", response_model=PinResetStartResponse)
def send_pin_reset_sms(
    payload: PinResetSmsRequest,
    session: SessionDependency,
    settings: SettingsDependency,
    sender: PasswordSmsSenderDependency,
) -> PinResetStartResponse:
    result = PinManagementService(session, settings).send_reset_sms(payload, sender)
    return PinResetStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/username-recovery/start", response_model=PinResetStartResponse)
def start_username_recovery(
    payload: PinResetStartRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    sender: PasswordEmailSenderDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> PinResetStartResponse:
    result = PinManagementService(session, settings).start_username_recovery(
        payload,
        sender,
        router_factory,
        requested_ip=request.client.host if request.client else None,
    )
    return PinResetStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/username-recovery/complete", response_model=UsernameRecoveryResponse)
def complete_username_recovery(
    payload: UsernameRecoveryCompleteRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> UsernameRecoveryResponse:
    username = PinManagementService(session, settings).complete_username_recovery(
        payload,
        router_factory,
        ip_address=request.client.host if request.client else None,
    )
    return UsernameRecoveryResponse(username=username)


@router.post("/pin-reset/complete", response_model=ChangePinResponse)
def complete_pin_reset(
    payload: PinResetCompleteRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> ChangePinResponse:
    try:
        pin_hasher = Argon2PinHasher.from_settings(settings)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PIN reset is not configured.",
        ) from exc
    PinManagementService(session, settings).complete_reset(
        payload,
        pin_hasher,
        router_factory,
        ip_address=request.client.host if request.client else None,
    )
    return ChangePinResponse()


@router.post("/account-unlock/start", response_model=PinResetStartResponse)
def start_account_unlock(
    payload: AccountUnlockStartRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    sender: PasswordEmailSenderDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> PinResetStartResponse:
    result = PinManagementService(session, settings).start_account_unlock(
        payload,
        sender,
        router_factory,
        requested_ip=request.client.host if request.client else None,
    )
    return PinResetStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/account-unlock/complete", response_model=AccountUnlockResponse)
def complete_account_unlock(
    payload: AccountUnlockCompleteRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    router_factory: PasswordRouterFactoryDependency,
) -> AccountUnlockResponse:
    PinManagementService(session, settings).complete_account_unlock(
        payload,
        router_factory,
        ip_address=request.client.host if request.client else None,
    )
    return AccountUnlockResponse()
