from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.core.security import Argon2PinHasher, PinHasher
from app.db.session import get_db_session
from app.integrations.brevo.client import BrevoEmailSender, EmailDeliveryError, OtpEmailSender
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.schemas.registration import (
    RegistrationCompleteRequest,
    RegistrationCompleteResponse,
    RegistrationRouterReadinessResponse,
    RegistrationStartRequest,
    RegistrationStartResponse,
    UsernameAvailabilityResponse,
    normalize_username,
)
from app.services.registration import (
    RegistrationAvailabilityService,
    RegistrationOtpService,
    RegistrationRouterReadinessService,
)

router = APIRouter(prefix="/api/registration", tags=["registration"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[Session, Depends(get_db_session)]


def get_otp_email_sender(settings: SettingsDependency) -> OtpEmailSender:
    try:
        return BrevoEmailSender.from_settings(settings)
    except EmailDeliveryError:
        # Let the service return the same safe unavailable response as provider failures.
        return _UnavailableEmailSender()


class _UnavailableEmailSender:
    def send_registration_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Brevo transactional email is not configured.")

    def send_pin_reset_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Brevo transactional email is not configured.")

    def send_username_recovery_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Brevo transactional email is not configured.")

    def send_account_unlock_otp(
        self, *, recipient: str, code: str, expires_in_minutes: int
    ) -> None:
        raise EmailDeliveryError("Brevo transactional email is not configured.")


EmailSenderDependency = Annotated[OtpEmailSender, Depends(get_otp_email_sender)]


def get_pin_hasher(settings: SettingsDependency) -> PinHasher:
    try:
        return Argon2PinHasher.from_settings(settings)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PIN hashing is not configured.",
        ) from exc


PinHasherDependency = Annotated[PinHasher, Depends(get_pin_hasher)]
RouterClientFactory = Callable[[str], MikroTikClient]


def get_registration_router_client_factory(
    settings: SettingsDependency,
    session: SessionDependency,
) -> RouterClientFactory:
    def create_client(router_id: str) -> MikroTikClient:
        router_definition = get_router(session, router_id)
        return MikroTikClient(MikroTikConfig.from_settings(router_definition, settings))

    return create_client


RouterClientFactoryDependency = Annotated[
    RouterClientFactory,
    Depends(get_registration_router_client_factory),
]


@router.get("/username-availability", response_model=UsernameAvailabilityResponse)
def username_availability(
    username: str,
    session: SessionDependency,
) -> UsernameAvailabilityResponse:
    try:
        normalized_username = normalize_username(username)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Username format is invalid.",
        ) from exc

    result = RegistrationAvailabilityService(session).check_username(normalized_username)
    return UsernameAvailabilityResponse(
        username=result.username,
        available=result.available,
        suggestions=result.suggestions,
    )


@router.get("/router-readiness", response_model=RegistrationRouterReadinessResponse)
def router_readiness(
    router_id: str,
    username: str,
    settings: SettingsDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> RegistrationRouterReadinessResponse:
    normalized_router_id = router_id.strip()
    try:
        normalized_username = normalize_username(username)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Username format is invalid.",
        ) from exc

    try:
        router_client = router_client_factory(normalized_router_id)
    except UnknownRouterError as exc:
        raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.") from exc
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Signup is currently unavailable. Please contact help and support.",
        ) from exc

    try:
        RegistrationRouterReadinessService(settings).check(
            router_client,
            normalized_username,
        )
    finally:
        with suppress(Exception):
            router_client.disconnect()

    return RegistrationRouterReadinessResponse(
        router_id=normalized_router_id,
        username=normalized_username,
        ready=True,
    )


@router.post(
    "/start",
    response_model=RegistrationStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_registration(
    payload: RegistrationStartRequest,
    request: Request,
    session: SessionDependency,
    sender: EmailSenderDependency,
    settings: SettingsDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> RegistrationStartResponse:
    try:
        router_client = router_client_factory(payload.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.") from exc
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Signup is currently unavailable. Please contact help and support.",
        ) from exc

    try:
        result = RegistrationOtpService(session, sender, settings).start(
            payload,
            router_client,
            requested_ip=request.client.host if request.client else None,
        )
    finally:
        with suppress(Exception):
            router_client.disconnect()

    return RegistrationStartResponse(
        challenge_id=result.challenge_id,
        destination=result.destination,
        expires_in_seconds=result.expires_in_seconds,
        resend_after_seconds=result.resend_after_seconds,
    )


@router.post("/complete", response_model=RegistrationCompleteResponse)
def complete_registration(
    payload: RegistrationCompleteRequest,
    session: SessionDependency,
    sender: EmailSenderDependency,
    settings: SettingsDependency,
    pin_hasher: PinHasherDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> RegistrationCompleteResponse:
    try:
        router_client = router_client_factory(payload.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.") from exc
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Router access is not configured.",
        ) from exc

    try:
        completed = RegistrationOtpService(session, sender, settings).complete(
            payload,
            router_client,
            pin_hasher,
        )
    finally:
        with suppress(Exception):
            router_client.disconnect()

    return RegistrationCompleteResponse(
        customer_id=completed.customer_id,
        username=completed.username,
        account_status=completed.account_status,
        router_user_disabled=completed.router_user_disabled,
    )
