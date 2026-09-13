from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.integrations.paystack import (
    InitializedTransaction,
    PaystackError,
    PaystackGateway,
    VerifiedTransaction,
)
from app.models.activation import Activation
from app.models.customer import Customer
from app.models.enums import ActivationStatus, ActivationTrigger, PaymentStatus
from app.models.package import Package, RouterPackageProfile
from app.models.transaction import Transaction
from app.services.package_activation import PackageActivationService, RouterClientFactory


@dataclass(frozen=True, slots=True)
class PaymentProcessingResult:
    reference: str
    payment_status: PaymentStatus
    activation_status: ActivationStatus | None
    plan_name: str


class PaymentVerificationError(RuntimeError):
    """Raised when a provider response cannot be matched to the local purchase."""


class FreePlanClaimService:
    """Create and activate a zero-cost promotion without contacting Paystack."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        router_client_factory: RouterClientFactory,
    ) -> None:
        self._session = session
        self._activation_service = PackageActivationService(
            session,
            router_client_factory,
            settings,
        )

    def claim(self, customer: Customer, package_id: uuid.UUID) -> PaymentProcessingResult:
        self._session.scalar(
            select(Customer).where(Customer.id == customer.id).with_for_update()
        )
        mapping = self._session.scalar(
            select(RouterPackageProfile)
            .options(joinedload(RouterPackageProfile.package))
            .join(RouterPackageProfile.package)
            .where(
                RouterPackageProfile.router_id == customer.router_id,
                RouterPackageProfile.package_id == package_id,
                RouterPackageProfile.is_active.is_(True),
                Package.is_active.is_(True),
            )
        )
        if mapping is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Plan is not available.")
        package = mapping.package
        if package.amount != Decimal(0) or not package.is_promotional:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Only free promotional plans can be claimed without payment.",
            )

        existing = self._session.scalar(
            select(Transaction)
            .options(selectinload(Transaction.activation), selectinload(Transaction.package))
            .where(
                Transaction.customer_id == customer.id,
                Transaction.package_id == package.id,
                Transaction.payment_status == PaymentStatus.SUCCESS,
            )
            .order_by(Transaction.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            activation_status = existing.activation.status if existing.activation else None
            if existing.activation is not None and activation_status not in {
                ActivationStatus.SUCCESS,
                ActivationStatus.SUPERSEDED,
                ActivationStatus.MANUAL_REVIEW,
            }:
                activation_status = self._activation_service.activate(
                    existing.activation,
                    trigger=ActivationTrigger.CUSTOMER_RETRY,
                )
            return PaymentProcessingResult(
                reference=existing.paystack_reference,
                payment_status=existing.payment_status,
                activation_status=activation_status,
                plan_name=existing.package.name,
            )

        now = datetime.now(UTC)
        reference = f"FREE-{uuid.uuid4().hex.upper()}"
        transaction = Transaction(
            customer_id=customer.id,
            package_id=package.id,
            router_id=customer.router_id,
            paystack_reference=reference,
            amount=Decimal(0),
            currency=package.currency,
            payment_status=PaymentStatus.SUCCESS,
            provider_status="free_promotion",
            paid_at=now,
        )
        activation = Activation(
            transaction=transaction,
            customer_id=customer.id,
            package_id=package.id,
            router_id=customer.router_id,
            target_profile=mapping.mikrotik_profile,
            target_disabled=False,
        )
        bind = self._session.get_bind()
        if bind.dialect.name == "sqlite":
            activation.sequence_number = (
                self._session.scalar(select(func.max(Activation.sequence_number))) or 0
            ) + 1
        self._session.add_all([transaction, activation])
        self._session.commit()
        activation_status = self._activation_service.activate(
            activation,
            trigger=ActivationTrigger.CUSTOMER_RETRY,
        )
        return PaymentProcessingResult(
            reference=reference,
            payment_status=PaymentStatus.SUCCESS,
            activation_status=activation_status,
            plan_name=package.name,
        )

    def retry(self, customer: Customer, reference: str) -> PaymentProcessingResult:
        transaction = self._session.scalar(
            select(Transaction)
            .options(selectinload(Transaction.activation), selectinload(Transaction.package))
            .where(
                Transaction.customer_id == customer.id,
                Transaction.paystack_reference == reference,
                Transaction.provider_status == "free_promotion",
                Transaction.amount == 0,
            )
        )
        if transaction is None or transaction.activation is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Free plan claim was not found.")
        activation_status = self._activation_service.activate(
            transaction.activation,
            trigger=ActivationTrigger.CUSTOMER_RETRY,
        )
        return PaymentProcessingResult(
            reference=transaction.paystack_reference,
            payment_status=transaction.payment_status,
            activation_status=activation_status,
            plan_name=transaction.package.name,
        )


class PaymentVerificationService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        gateway: PaystackGateway,
        router_client_factory: RouterClientFactory,
    ) -> None:
        self._session = session
        self._settings = settings
        self._gateway = gateway
        self._router_client_factory = router_client_factory
        self._activation_service = PackageActivationService(
            session,
            router_client_factory,
            settings,
        )

    def initialize(
        self,
        customer: Customer,
        package_id: uuid.UUID,
    ) -> InitializedTransaction:
        mapping = self._session.scalar(
            select(RouterPackageProfile)
            .options(
                joinedload(RouterPackageProfile.package),
                joinedload(RouterPackageProfile.router),
            )
            .join(RouterPackageProfile.package)
            .where(
                RouterPackageProfile.router_id == customer.router_id,
                RouterPackageProfile.package_id == package_id,
                RouterPackageProfile.is_active.is_(True),
                Package.is_active.is_(True),
            )
        )
        if mapping is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Plan is not available.")
        if mapping.package.amount <= 0:
            raise ServiceError(status.HTTP_409_CONFLICT, "Plan cannot be purchased online.")
        if mapping.package.is_promotional and self._session.scalar(
            select(Transaction.id)
            .where(
                Transaction.customer_id == customer.id,
                Transaction.package_id == mapping.package.id,
                Transaction.payment_status == PaymentStatus.SUCCESS,
            )
            .limit(1)
        ):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "This promotional plan has already been used.",
            )
        callback_url = (self._settings.paystack_callback_url or "").strip()
        if not callback_url:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Payments are not configured.",
            )

        self._ensure_router_ready(
            router_id=customer.router_id,
            username=customer.username,
            profile=mapping.mikrotik_profile,
        )

        reference = f"VLAD-{uuid.uuid4().hex.upper()}"
        transaction = Transaction(
            customer_id=customer.id,
            package_id=mapping.package.id,
            router_id=customer.router_id,
            paystack_reference=reference,
            amount=mapping.package.amount,
            currency=mapping.package.currency,
            payment_status=PaymentStatus.PENDING,
            provider_status="initializing",
        )
        activation = Activation(
            transaction=transaction,
            customer_id=customer.id,
            package_id=mapping.package.id,
            router_id=customer.router_id,
            target_profile=mapping.mikrotik_profile,
            target_disabled=False,
        )
        sqlite_sequence = self._next_sqlite_sequence()
        if sqlite_sequence is not None:
            activation.sequence_number = sqlite_sequence
        self._session.add_all([transaction, activation])
        self._session.commit()

        amount_minor = _minor_units(mapping.package.amount)
        try:
            initialize_arguments: dict[str, object] = {
                "email": customer.email,
                "amount": amount_minor,
                "currency": mapping.package.currency,
                "reference": reference,
                "callback_url": callback_url,
                "metadata": {
                    "customer_id": str(customer.id),
                    "package_id": str(mapping.package.id),
                    "router_id": customer.router_id,
                    "plan_name": mapping.display_name or mapping.package.name,
                },
            }
            split_code = (mapping.router.paystack_split_code or "").strip()
            if split_code:
                initialize_arguments["split_code"] = split_code
            initialized = self._gateway.initialize_transaction(
                **initialize_arguments,
            )
        except PaystackError:
            transaction.provider_status = "initialize_error"
            transaction.failure_code = "paystack_initialize_error"
            transaction.failure_message = "Payment checkout could not be initialized."
            self._session.commit()
            raise

        transaction.provider_status = "initialized"
        transaction.failure_code = None
        transaction.failure_message = None
        self._session.commit()
        return initialized

    def _ensure_router_ready(self, *, router_id: str, username: str, profile: str) -> None:
        router_client = None
        try:
            router_client = self._router_client_factory(router_id)
            hotspot_user = router_client.get_hotspot_user(username)
            hotspot_profile = router_client.get_hotspot_user_profile(profile)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The router is currently unreachable. Please contact support.",
            ) from exc
        finally:
            if router_client is not None:
                with suppress(Exception):
                    router_client.disconnect()

        if hotspot_user is None or hotspot_profile is None:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The router is not ready to activate this plan. Please contact support.",
            )

    def verify(
        self,
        reference: str,
        *,
        trigger: ActivationTrigger,
    ) -> PaymentProcessingResult:
        transaction = self._session.scalar(
            select(Transaction)
            .options(
                selectinload(Transaction.customer),
                selectinload(Transaction.package),
                selectinload(Transaction.activation),
            )
            .where(Transaction.paystack_reference == reference)
            .with_for_update()
        )
        if transaction is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Purchase was not found.")

        if transaction.payment_status != PaymentStatus.SUCCESS:
            try:
                verified = self._gateway.verify_transaction(reference)
            except PaystackError:
                transaction.failure_code = "paystack_verification_error"
                transaction.failure_message = "Payment verification is temporarily unavailable."
                self._session.commit()
                raise
            self._apply_verified_payment(transaction, verified)

        activation_status = transaction.activation.status if transaction.activation else None
        if (
            transaction.payment_status == PaymentStatus.SUCCESS
            and transaction.activation is not None
            and transaction.activation.status
            not in {ActivationStatus.SUCCESS, ActivationStatus.SUPERSEDED}
        ):
            activation_status = self._activation_service.activate(
                transaction.activation,
                trigger=trigger,
            )
        return PaymentProcessingResult(
            reference=transaction.paystack_reference,
            payment_status=transaction.payment_status,
            activation_status=activation_status,
            plan_name=transaction.package.name,
        )

    def result_for_customer(
        self,
        customer: Customer,
        reference: str,
    ) -> PaymentProcessingResult:
        transaction = self._session.scalar(
            select(Transaction)
            .options(joinedload(Transaction.package), joinedload(Transaction.activation))
            .where(
                Transaction.paystack_reference == reference,
                Transaction.customer_id == customer.id,
            )
        )
        if transaction is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Purchase was not found.")
        return PaymentProcessingResult(
            reference=transaction.paystack_reference,
            payment_status=transaction.payment_status,
            activation_status=(transaction.activation.status if transaction.activation else None),
            plan_name=transaction.package.name,
        )

    def _apply_verified_payment(
        self,
        transaction: Transaction,
        verified: VerifiedTransaction,
    ) -> None:
        expected_metadata = {
            "customer_id": str(transaction.customer_id),
            "package_id": str(transaction.package_id),
            "router_id": transaction.router_id,
        }
        provider_metadata = {key: str(verified.metadata.get(key, "")) for key in expected_metadata}
        matches = (
            verified.reference == transaction.paystack_reference
            and verified.amount == _minor_units(transaction.amount)
            and verified.currency == transaction.currency
            and verified.customer_email == transaction.customer.email.casefold()
            and provider_metadata == expected_metadata
        )
        transaction.provider_status = verified.status[:80]
        if not matches:
            transaction.failure_code = "payment_verification_mismatch"
            transaction.failure_message = "Verified payment details did not match the purchase."
            self._session.commit()
            raise PaymentVerificationError("Verified payment details do not match.")

        if verified.status == "success":
            transaction.payment_status = PaymentStatus.SUCCESS
            transaction.paid_at = verified.paid_at or datetime.now(UTC)
            transaction.failed_at = None
            transaction.failure_code = None
            transaction.failure_message = None
        elif verified.status in {"abandoned", "failed", "reversed"}:
            transaction.payment_status = PaymentStatus.FAILED
            transaction.failed_at = datetime.now(UTC)
            transaction.failure_code = f"paystack_{verified.status}"
            transaction.failure_message = "Payment was not completed."
        else:
            transaction.payment_status = PaymentStatus.PENDING
            transaction.failure_code = None
            transaction.failure_message = None
        self._session.commit()

    def _next_sqlite_sequence(self) -> int | None:
        bind = self._session.get_bind()
        if bind.dialect.name != "sqlite":
            return None
        return (self._session.scalar(select(func.max(Activation.sequence_number))) or 0) + 1


def _minor_units(amount: Decimal) -> int:
    return int(amount.quantize(Decimal("0.01")) * 100)
