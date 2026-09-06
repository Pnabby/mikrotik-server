from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import get_router
from app.integrations.paystack import PaystackClient, PaystackError, PaystackGateway
from app.models.customer import Customer
from app.models.enums import ActivationStatus, ActivationTrigger, PaymentEventStatus, PaymentStatus
from app.models.payment_event import PaymentEvent
from app.models.transaction import Transaction
from app.routes.auth import get_authenticated_customer
from app.schemas.payments import (
    PaymentResultResponse,
    PaystackWebhookResponse,
    PurchaseInitializeRequest,
    PurchaseInitializeResponse,
)
from app.services.package_activation import RouterClientFactory
from app.services.payment_verification import (
    PaymentProcessingResult,
    PaymentVerificationError,
    PaymentVerificationService,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])
logger = logging.getLogger(__name__)
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
CustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]


def get_paystack_gateway(settings: SettingsDependency) -> PaystackGateway:
    try:
        return PaystackClient.from_settings(settings)
    except PaystackError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Payments are not configured.",
        ) from exc


PaystackGatewayDependency = Annotated[PaystackGateway, Depends(get_paystack_gateway)]


def get_payment_router_client_factory(
    settings: SettingsDependency,
    session: SessionDependency,
) -> RouterClientFactory:
    def create_client(router_id: str) -> MikroTikClient:
        router_definition = get_router(session, router_id)
        return MikroTikClient(MikroTikConfig.from_settings(router_definition, settings))

    return create_client


RouterClientFactoryDependency = Annotated[
    Callable[[str], MikroTikClient],
    Depends(get_payment_router_client_factory),
]


@router.post(
    "/initialize",
    response_model=PurchaseInitializeResponse,
    status_code=status.HTTP_201_CREATED,
)
def initialize_payment(
    payload: PurchaseInitializeRequest,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    gateway: PaystackGatewayDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> PurchaseInitializeResponse:
    try:
        initialized = PaymentVerificationService(
            session,
            settings,
            gateway,
            router_client_factory,
        ).initialize(customer, payload.package_id)
    except PaystackError as exc:
        raise ServiceError(
            status.HTTP_502_BAD_GATEWAY,
            "Payment checkout is temporarily unavailable.",
        ) from exc
    return PurchaseInitializeResponse(
        reference=initialized.reference,
        authorization_url=initialized.authorization_url,
    )


@router.get("/paystack/callback", include_in_schema=False)
def paystack_callback(
    settings: SettingsDependency,
    session: SessionDependency,
    gateway: PaystackGatewayDependency,
    router_client_factory: RouterClientFactoryDependency,
    reference: str | None = None,
    trxref: str | None = None,
) -> RedirectResponse:
    payment_reference = (reference or trxref or "").strip()
    outcome = "failed"
    if payment_reference:
        try:
            result = PaymentVerificationService(
                session,
                settings,
                gateway,
                router_client_factory,
            ).verify(
                payment_reference,
                trigger=ActivationTrigger.PAYMENT_VERIFICATION,
            )
            outcome = _browser_outcome(result)
        except PaystackError:
            outcome = "pending"
        except (PaymentVerificationError, ServiceError):
            outcome = "failed"
        except Exception:
            session.rollback()
            logger.exception(
                "Unexpected Paystack callback failure for reference %s",
                payment_reference,
            )
            outcome = "pending"

    account_url = f"{settings.frontend_url.rstrip('/')}/account"
    query = urlencode({"payment": outcome, "reference": payment_reference})
    return RedirectResponse(f"{account_url}?{query}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/paystack/webhook", response_model=PaystackWebhookResponse)
async def paystack_webhook(
    request: Request,
    settings: SettingsDependency,
    session: SessionDependency,
    gateway: PaystackGatewayDependency,
    router_client_factory: RouterClientFactoryDependency,
    x_paystack_signature: Annotated[str | None, Header()] = None,
) -> PaystackWebhookResponse:
    raw_body = await request.body()
    if len(raw_body) > 1_000_000:
        raise ServiceError(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook is too large.")
    if not _valid_signature(settings, raw_body, x_paystack_signature):
        raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature.")
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid webhook payload.") from exc
    if not isinstance(payload, dict):
        raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid webhook payload.")

    event_key = f"paystack:{hashlib.sha256(raw_body).hexdigest()}"
    payment_event = session.scalar(
        select(PaymentEvent).where(PaymentEvent.event_key == event_key).with_for_update()
    )
    if payment_event is not None and payment_event.status in {
        PaymentEventStatus.PROCESSED,
        PaymentEventStatus.IGNORED,
    }:
        return PaystackWebhookResponse()

    event_type = _text(payload.get("event")) or "unknown"
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    payment_reference = _text(data.get("reference")) if isinstance(data, dict) else ""
    if payment_event is None:
        payment_event = PaymentEvent(
            event_key=event_key,
            paystack_reference=payment_reference or None,
            event_type=event_type,
            payload=payload,
        )
        session.add(payment_event)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            payment_event = session.scalar(
                select(PaymentEvent).where(PaymentEvent.event_key == event_key)
            )
            if payment_event is None:
                raise
            if payment_event.status in {
                PaymentEventStatus.PROCESSED,
                PaymentEventStatus.IGNORED,
            }:
                return PaystackWebhookResponse()

    if event_type != "charge.success" or not payment_reference:
        payment_event.status = PaymentEventStatus.IGNORED
        payment_event.processed_at = datetime.now(UTC)
        session.commit()
        return PaystackWebhookResponse()

    try:
        PaymentVerificationService(
            session,
            settings,
            gateway,
            router_client_factory,
        ).verify(
            payment_reference,
            trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
        )
    except PaystackError as exc:
        payment_event.status = PaymentEventStatus.FAILED
        payment_event.processing_error = "Paystack verification is temporarily unavailable."
        session.commit()
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Payment verification is temporarily unavailable.",
        ) from exc
    except (PaymentVerificationError, ServiceError):
        payment_event.status = PaymentEventStatus.FAILED
        payment_event.processing_error = "The event could not be matched to a purchase."
        payment_event.processed_at = datetime.now(UTC)
        session.commit()
        return PaystackWebhookResponse()

    payment_event.transaction_id = session.scalar(
        select(Transaction.id).where(Transaction.paystack_reference == payment_reference)
    )
    payment_event.status = PaymentEventStatus.PROCESSED
    payment_event.processing_error = None
    payment_event.processed_at = datetime.now(UTC)
    session.commit()
    return PaystackWebhookResponse()


@router.post("/{reference}/verify", response_model=PaymentResultResponse)
def verify_customer_payment(
    reference: str,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    gateway: PaystackGatewayDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> PaymentResultResponse:
    service = PaymentVerificationService(
        session,
        settings,
        gateway,
        router_client_factory,
    )
    normalized_reference = reference.strip()
    # Establish ownership before a customer can trigger verification or activation.
    service.result_for_customer(customer, normalized_reference)
    try:
        result = service.verify(
            normalized_reference,
            trigger=ActivationTrigger.CUSTOMER_RETRY,
        )
    except PaystackError as exc:
        raise ServiceError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Payment verification is temporarily unavailable.",
        ) from exc
    except PaymentVerificationError as exc:
        raise ServiceError(
            status.HTTP_409_CONFLICT,
            "Payment details could not be matched.",
        ) from exc
    return _payment_result_response(result)


@router.get("/{reference}", response_model=PaymentResultResponse)
def payment_result(
    reference: str,
    customer: CustomerDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    gateway: PaystackGatewayDependency,
    router_client_factory: RouterClientFactoryDependency,
) -> PaymentResultResponse:
    result = PaymentVerificationService(
        session,
        settings,
        gateway,
        router_client_factory,
    ).result_for_customer(customer, reference.strip())
    return _payment_result_response(result)


def _valid_signature(settings: Settings, body: bytes, supplied_signature: str | None) -> bool:
    secret = settings.paystack_webhook_secret or settings.paystack_secret_key
    if secret is None or not supplied_signature:
        return False
    expected = hmac.new(
        secret.get_secret_value().strip().encode("utf-8"),
        body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied_signature.strip().casefold())


def _browser_outcome(result: PaymentProcessingResult) -> str:
    if result.payment_status == PaymentStatus.FAILED:
        return "failed"
    if result.payment_status != PaymentStatus.SUCCESS:
        return "pending"
    if result.activation_status == ActivationStatus.SUCCESS:
        return "active"
    if result.activation_status == ActivationStatus.SUPERSEDED:
        return "promo_already_used"
    return "activation_pending"


def _payment_result_response(result: PaymentProcessingResult) -> PaymentResultResponse:
    return PaymentResultResponse(
        reference=result.reference,
        payment_status=result.payment_status,
        activation_status=result.activation_status,
        plan_name=result.plan_name,
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
