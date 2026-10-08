from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.activation import Activation
from app.models.activation_attempt import ActivationAttempt
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import (
    AccountStatus,
    ActivationAttemptOutcome,
    ActivationStatus,
    ActivationTrigger,
    AuditActorType,
    SubscriptionStatus,
)
from app.models.hostel_transfer import HostelTransferOperation
from app.models.package import Package
from app.models.router import Router
from app.models.subscription import Subscription
from app.services.notifications import CustomerNotificationService
from app.services.transfer_lock import transfer_lock


class ActivationRouterClient(Protocol):
    def get_hotspot_user(self, username: str) -> dict[str, str] | None: ...

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None: ...

    def activate_hotspot_user(
        self,
        *,
        username: str,
        profile: str,
        comment: str,
        data_limit_bytes: int | None,
    ) -> dict[str, str]: ...

    def disconnect(self) -> None: ...


RouterClientFactory = Callable[[str], ActivationRouterClient]
ACTIVATION_CLAIM_TTL = timedelta(seconds=30)


class PackageActivationService:
    """Idempotently apply a verified purchase to RouterOS and start access."""

    def __init__(
        self,
        session: Session,
        router_client_factory: RouterClientFactory,
        settings: Settings,
    ) -> None:
        self._session = session
        self._router_client_factory = router_client_factory
        self._notifications = CustomerNotificationService(settings)

    def activate(
        self,
        activation: Activation,
        *,
        trigger: ActivationTrigger,
    ) -> ActivationStatus:
        # A checkout may be paid while its customer is moving. Share the move's
        # lock across commits, and leave verified payment durable for the normal
        # activation retry once transfer/recovery has finished.
        try:
            with transfer_lock(self._session, activation.customer_id):
                pending_transfer = self._session.scalar(
                    select(HostelTransferOperation.id).where(
                        HostelTransferOperation.customer_id == activation.customer_id,
                        HostelTransferOperation.is_active.is_(True),
                    ).limit(1)
                )
                if pending_transfer is not None:
                    return activation.status
                return self._activate(activation, trigger=trigger)
        except ServiceError as exc:
            if exc.error_code != "hostel_transfer_in_progress":
                raise
            return activation.status

    def _activate(
        self,
        activation: Activation,
        *,
        trigger: ActivationTrigger,
    ) -> ActivationStatus:
        activation = self._session.scalar(
            select(Activation).where(Activation.id == activation.id).with_for_update()
        )
        if activation is None:
            return ActivationStatus.MANUAL_REVIEW
        if activation.status in {ActivationStatus.SUCCESS, ActivationStatus.SUPERSEDED}:
            if activation.status == ActivationStatus.SUCCESS:
                self._notify_activation(activation)
            return activation.status

        if activation.status == ActivationStatus.NOT_STARTED and activation.attempt_count == 0:
            # A never-applied purchase follows the customer's current hostel.
            # Read the database column so a cached customer cannot send a late
            # payment callback to the old router. Keep the transaction's hostel
            # and completed activation history intact for financial attribution.
            current_router_id = self._session.scalar(
                select(Customer.router_id).where(Customer.id == activation.customer_id)
            )
            if current_router_id is not None:
                activation.router_id = current_router_id

        router = self._session.get(Router, activation.router_id)
        if router is not None and not router.is_active:
            return activation.status

        claim_time = datetime.now(UTC)
        if (
            activation.status in {ActivationStatus.PROCESSING, ActivationStatus.PROVISIONING}
            and activation.last_attempt_at is not None
            and claim_time - _as_utc(activation.last_attempt_at) < ACTIVATION_CLAIM_TTL
        ):
            return activation.status

        customer = self._session.get(Customer, activation.customer_id)
        package = self._session.get(Package, activation.package_id)
        if customer is None or package is None:
            return self._finish_without_router(
                activation,
                trigger=trigger,
                status=ActivationStatus.MANUAL_REVIEW,
                outcome=ActivationAttemptOutcome.MANUAL_REVIEW,
                error_code="activation_records_missing",
            )

        if package.is_promotional and self._session.scalar(
            select(Subscription.id)
            .where(
                Subscription.customer_id == customer.id,
                Subscription.package_id == package.id,
                Subscription.transaction_id != activation.transaction_id,
            )
            .limit(1)
        ):
            return self._finish_without_router(
                activation,
                trigger=trigger,
                status=ActivationStatus.SUPERSEDED,
                outcome=ActivationAttemptOutcome.SUPERSEDED,
                error_code="promotional_plan_already_claimed",
            )

        now = datetime.now(UTC)
        attempt = ActivationAttempt(
            activation_id=activation.id,
            attempt_number=activation.attempt_count + 1,
            trigger=trigger,
        )
        activation.attempt_count += 1
        activation.last_attempt_at = now
        activation.status = ActivationStatus.PROCESSING
        activation.next_retry_at = None
        activation.last_error_code = None
        activation.last_error_message = None
        self._session.add(attempt)
        # Persist intent before touching RouterOS. If the process dies after the write,
        # reconciliation can inspect the activation marker and safely finish the job.
        self._session.commit()

        router_client: ActivationRouterClient | None = None
        try:
            router_client = self._router_client_factory(activation.router_id)
            hotspot_user = router_client.get_hotspot_user(customer.username)
            profile = router_client.get_hotspot_user_profile(activation.target_profile)
        except Exception:  # noqa: BLE001 - RouterOS adapters raise multiple library errors.
            if router_client is not None:
                with suppress(Exception):
                    router_client.disconnect()
            return self._finish_attempt(
                activation,
                attempt,
                status=ActivationStatus.RETRY_REQUIRED,
                outcome=ActivationAttemptOutcome.RETRY_REQUIRED,
                error_code="router_unavailable",
                retry=True,
            )

        if hotspot_user is None:
            with suppress(Exception):
                router_client.disconnect()
            return self._finish_attempt(
                activation,
                attempt,
                status=ActivationStatus.MANUAL_REVIEW,
                outcome=ActivationAttemptOutcome.MANUAL_REVIEW,
                error_code="hotspot_user_missing",
            )
        if profile is None:
            with suppress(Exception):
                router_client.disconnect()
            return self._finish_attempt(
                activation,
                attempt,
                status=ActivationStatus.MANUAL_REVIEW,
                outcome=ActivationAttemptOutcome.MANUAL_REVIEW,
                error_code="hotspot_profile_missing",
            )

        attempt.router_state_before = _router_state(hotspot_user)
        attempt.observed_activation_id = _activation_marker(hotspot_user.get("comment"))
        attempt.observed_profile = _text(hotspot_user.get("profile")) or None
        attempt.observed_disabled = _router_bool(hotspot_user.get("disabled"))
        activation.status = ActivationStatus.PROVISIONING
        self._session.commit()

        # Buying a plan makes it ready, but does not start its validity clock.
        # RouterOS adds the login timestamp only when the captive portal accepts
        # the customer's first login.
        activation_comment = f"activation={activation.activation_id}"
        if _matches_target(hotspot_user, activation, package):
            # A previous attempt reached RouterOS but did not finish its database commit.
            # The activation marker makes it safe to finalize without resetting quota twice.
            updated_user = hotspot_user
            with suppress(Exception):
                router_client.disconnect()
        else:
            try:
                router_client.activate_hotspot_user(
                    username=customer.username,
                    profile=activation.target_profile,
                    comment=activation_comment,
                    data_limit_bytes=package.data_limit_bytes,
                )
                updated_user = router_client.get_hotspot_user(customer.username)
            except Exception:  # noqa: BLE001 - a failed write is deliberately reconciled.
                # The write may have reached the router before the connection failed.
                return self._finish_attempt(
                    activation,
                    attempt,
                    status=ActivationStatus.RECONCILIATION_REQUIRED,
                    outcome=ActivationAttemptOutcome.RECONCILIATION_REQUIRED,
                    error_code="router_write_unconfirmed",
                    retry=True,
                )
            finally:
                with suppress(Exception):
                    router_client.disconnect()

        attempt.router_state_after = _router_state(updated_user)
        attempt.observed_activation_id = _activation_marker(
            updated_user.get("comment") if updated_user else None
        )
        attempt.observed_profile = _text(updated_user.get("profile")) if updated_user else None
        attempt.observed_disabled = (
            _router_bool(updated_user.get("disabled")) if updated_user else None
        )
        if not _matches_target(updated_user, activation, package):
            return self._finish_attempt(
                activation,
                attempt,
                status=ActivationStatus.RECONCILIATION_REQUIRED,
                outcome=ActivationAttemptOutcome.RECONCILIATION_REQUIRED,
                error_code="router_state_mismatch",
                retry=True,
            )

        completed_at = datetime.now(UTC)
        new_subscription = Subscription(
            id=uuid.uuid4(),
            customer_id=customer.id,
            package_id=package.id,
            transaction_id=activation.transaction_id,
            activation_id=activation.id,
            router_id=activation.router_id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=None,
            expires_at=None,
        )
        previous_subscriptions = self._session.scalars(
            select(Subscription)
            .where(
                Subscription.customer_id == customer.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.activation_id != activation.id,
            )
            .with_for_update()
        ).all()
        # The old subscriptions reference this row through superseded_by_id, so it
        # must exist before PostgreSQL applies those updates.
        self._session.add(new_subscription)
        self._session.flush()
        for previous in previous_subscriptions:
            previous.status = SubscriptionStatus.SUPERSEDED
            previous.ended_at = completed_at
            previous.superseded_by_id = new_subscription.id

        activation.status = ActivationStatus.SUCCESS
        activation.confirmed_at = completed_at
        activation.next_retry_at = None
        activation.last_error_code = None
        activation.last_error_message = None
        attempt.outcome = ActivationAttemptOutcome.SUCCESS
        attempt.finished_at = completed_at
        customer.account_status = AccountStatus.ACTIVE
        self._session.add_all(
            [
                AuditLog(
                    actor_type=AuditActorType.SYSTEM,
                    customer_id=customer.id,
                    action="package_activation.completed",
                    entity_type="activation",
                    entity_id=str(activation.id),
                    details={
                        "activation_id": activation.activation_id,
                        "transaction_id": str(activation.transaction_id),
                        "package_id": str(package.id),
                        "router_id": activation.router_id,
                    },
                ),
            ]
        )
        self._session.commit()
        self._notify_activation(activation, customer=customer, package=package)
        return activation.status

    def _notify_activation(
        self,
        activation: Activation,
        *,
        customer: Customer | None = None,
        package: Package | None = None,
    ) -> None:
        if activation.email_notified_at is not None:
            return
        customer = customer or self._session.get(Customer, activation.customer_id)
        package = package or self._session.get(Package, activation.package_id)
        if customer is None or package is None:
            return
        result = self._notifications.send_bundle_activated(
            customer,
            package.name,
            send_email=activation.email_notified_at is None,
        )
        now = datetime.now(UTC)
        if result.email_sent:
            activation.email_notified_at = now
        if result.email_sent:
            self._session.commit()

    def _finish_without_router(
        self,
        activation: Activation,
        *,
        trigger: ActivationTrigger,
        status: ActivationStatus,
        outcome: ActivationAttemptOutcome,
        error_code: str,
    ) -> ActivationStatus:
        now = datetime.now(UTC)
        activation.attempt_count += 1
        activation.last_attempt_at = now
        activation.status = status
        activation.last_error_code = error_code
        self._session.add(
            ActivationAttempt(
                activation_id=activation.id,
                attempt_number=activation.attempt_count,
                trigger=trigger,
                outcome=outcome,
                error_code=error_code,
                finished_at=now,
            )
        )
        self._session.commit()
        return activation.status

    def _finish_attempt(
        self,
        activation: Activation,
        attempt: ActivationAttempt,
        *,
        status: ActivationStatus,
        outcome: ActivationAttemptOutcome,
        error_code: str,
        retry: bool = False,
    ) -> ActivationStatus:
        now = datetime.now(UTC)
        activation.status = status
        activation.last_error_code = error_code
        activation.last_error_message = "Activation could not be confirmed automatically."
        activation.next_retry_at = now + timedelta(minutes=2) if retry else None
        attempt.outcome = outcome
        attempt.error_code = error_code
        attempt.error_message = activation.last_error_message
        attempt.finished_at = now
        self._session.commit()
        return activation.status


def _router_state(user: dict[str, str] | None) -> dict[str, object] | None:
    if user is None:
        return None
    return {
        "name": _text(user.get("name")),
        "profile": _text(user.get("profile")),
        "disabled": _router_bool(user.get("disabled")),
        "comment": _text(user.get("comment")),
        "limit_bytes_total": _router_int(user.get("limit-bytes-total")),
    }


def _matches_target(
    user: dict[str, str] | None,
    activation: Activation,
    package: Package,
) -> bool:
    if user is None:
        return False
    if _text(user.get("profile")).casefold() != activation.target_profile.casefold():
        return False
    if _router_bool(user.get("disabled")) is not activation.target_disabled:
        return False
    if _activation_marker(user.get("comment")) != activation.activation_id:
        return False
    if package.data_limit_bytes is not None:
        return _router_int(user.get("limit-bytes-total")) == package.data_limit_bytes
    return True


def _activation_marker(comment: object) -> str | None:
    if not isinstance(comment, str):
        return None
    for component in comment.split(";"):
        key, separator, value = component.partition("=")
        if separator and key.strip().casefold() == "activation":
            return value.strip() or None
    return None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _router_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().casefold() in {"yes", "true", "1", "on"}


def _router_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
