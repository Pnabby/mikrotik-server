from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.core.security import PasswordHasher, PinHasher
from app.models.activation import Activation
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import ActivationStatus, AuditActorType, SubscriptionStatus
from app.models.subscription import Subscription

logger = logging.getLogger(__name__)

_UNRESOLVED_ACTIVATION_STATUSES = {
    ActivationStatus.NOT_STARTED,
    ActivationStatus.PROCESSING,
    ActivationStatus.PROVISIONING,
    ActivationStatus.RETRY_REQUIRED,
    ActivationStatus.RECONCILIATION_REQUIRED,
}

_BYTE_LIMIT_FIELDS = {
    "limit-bytes-in": "bytes-in",
    "limit-bytes-out": "bytes-out",
    "limit-bytes-total": "bytes-total",
}


class HostelTransferRouterClient(Protocol):
    def get_hotspot_user(self, username: str) -> dict[str, str] | None: ...

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None: ...

    def clear_hotspot_authentication(self, username: str) -> dict[str, str] | None: ...

    def create_hotspot_user_copy(
        self,
        user: dict[str, str],
        *,
        byte_limits: dict[str, int | None],
    ) -> dict[str, str]: ...

    def delete_hotspot_user(self, username: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class HostelTransferResult:
    router_id: str
    router_name: str
    remaining_data_limit_bytes: int | None


class HostelTransferService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def transfer_with_pin(
        self,
        customer: Customer,
        *,
        pin: str,
        pin_hasher: PinHasher,
        destination_router_id: str,
        destination_router_name: str,
        source_client: HostelTransferRouterClient,
        destination_client: HostelTransferRouterClient,
        ip_address: str | None,
    ) -> HostelTransferResult:
        if not pin_hasher.verify(customer.pin_hash, pin):
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "The PIN is incorrect.")
        return self._transfer(
            customer,
            destination_router_id=destination_router_id,
            destination_router_name=destination_router_name,
            source_client=source_client,
            destination_client=destination_client,
            actor_type=AuditActorType.CUSTOMER,
            admin=None,
            ip_address=ip_address,
        )

    def transfer_with_admin_password(
        self,
        customer: Customer,
        *,
        admin: AdminUser,
        password: str,
        password_hasher: PasswordHasher,
        destination_router_id: str,
        destination_router_name: str,
        source_client: HostelTransferRouterClient,
        destination_client: HostelTransferRouterClient,
        ip_address: str | None,
    ) -> HostelTransferResult:
        if not password_hasher.verify(admin.password_hash, password):
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "The admin password is incorrect.")
        return self._transfer(
            customer,
            destination_router_id=destination_router_id,
            destination_router_name=destination_router_name,
            source_client=source_client,
            destination_client=destination_client,
            actor_type=AuditActorType.ADMIN,
            admin=admin,
            ip_address=ip_address,
        )

    def _transfer(
        self,
        customer: Customer,
        *,
        destination_router_id: str,
        destination_router_name: str,
        source_client: HostelTransferRouterClient,
        destination_client: HostelTransferRouterClient,
        actor_type: AuditActorType,
        admin: AdminUser | None,
        ip_address: str | None,
    ) -> HostelTransferResult:
        # Serialize moves for one account so simultaneous requests cannot remove
        # each other's newly-created destination copy.
        locked_customer = self._session.scalar(
            select(Customer).where(Customer.id == customer.id).with_for_update()
        )
        if locked_customer is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Customer was not found.")
        customer = locked_customer
        source_router_id = customer.router_id
        if destination_router_id == source_router_id:
            raise ServiceError(status.HTTP_409_CONFLICT, "The customer is already at this hostel.")
        unresolved_activation = next(
            iter(
                self._session.scalars(
                    select(Activation.id).where(
                        Activation.customer_id == customer.id,
                        Activation.status.in_(_UNRESOLVED_ACTIVATION_STATUSES),
                    )
                )
            ),
            None,
        )
        if unresolved_activation is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Finish the pending plan activation before changing hostels.",
            )

        source_user = source_client.get_hotspot_user(customer.username)
        if source_user is None:
            raise ServiceError(status.HTTP_409_CONFLICT, "The source network account is missing.")
        if destination_client.get_hotspot_user(customer.username) is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "That username already exists at the destination hostel.",
            )
        profile = str(source_user.get("profile") or "").strip()
        if not profile or destination_client.get_hotspot_user_profile(profile) is None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The customer's network profile is unavailable at the destination hostel.",
            )

        # This must happen before reading counters: RouterOS writes a terminated
        # session's final byte counts back to the user record.
        settled_user = source_client.clear_hotspot_authentication(customer.username)
        if settled_user is None:
            raise ServiceError(status.HTTP_409_CONFLICT, "The source network account is missing.")
        byte_limits = _remaining_byte_limits(settled_user)

        try:
            copied_user = destination_client.create_hotspot_user_copy(
                settled_user,
                byte_limits=byte_limits,
            )
            if not _copy_matches(settled_user, copied_user, byte_limits):
                raise RuntimeError("Destination HotSpot user did not match the transfer.")
        except Exception as exc:
            # The add may have reached RouterOS even when its read-back failed.
            self._remove_destination_copy(destination_client, customer.username)
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "The account could not be created at the destination hostel.",
            ) from exc

        try:
            source_deleted = source_client.delete_hotspot_user(customer.username)
        except Exception as exc:
            # A transport error can occur after RouterOS accepted the removal.
            # Only remove the new copy when we can confirm the old one survived;
            # if source state is unknown, retaining the copy avoids losing access.
            try:
                source_deleted = source_client.get_hotspot_user(customer.username) is None
            except Exception:  # noqa: BLE001 - RouterOS transport errors are not stable.
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "The previous hostel could not confirm account removal.",
                ) from exc
            if not source_deleted:
                self._remove_destination_copy(destination_client, customer.username)
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "The account could not be removed from the previous hostel.",
                ) from exc
        if not source_deleted:
            self._remove_destination_copy(destination_client, customer.username)
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "The account could not be removed from the previous hostel.",
            )

        customer.router_id = destination_router_id
        for subscription in self._session.scalars(
            select(Subscription).where(
                Subscription.customer_id == customer.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        ):
            subscription.router_id = destination_router_id
        self._session.add(
            AuditLog(
                actor_type=actor_type,
                admin_user_id=admin.id if admin else None,
                customer_id=customer.id,
                action="customer.hostel_transferred",
                entity_type="customer",
                entity_id=str(customer.id),
                details={
                    "username": customer.username,
                    "source_router_id": source_router_id,
                    "destination_router_id": destination_router_id,
                    "remaining_data_limit_bytes": byte_limits["limit-bytes-total"],
                },
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            self._restore_source_after_database_failure(
                source_client,
                destination_client,
                settled_user,
                byte_limits,
            )
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The hostel change could not be saved.",
            ) from exc

        return HostelTransferResult(
            router_id=destination_router_id,
            router_name=destination_router_name,
            remaining_data_limit_bytes=byte_limits["limit-bytes-total"],
        )

    @staticmethod
    def _remove_destination_copy(
        destination_client: HostelTransferRouterClient, username: str
    ) -> None:
        try:
            if not destination_client.delete_hotspot_user(username):
                logger.critical("Could not roll back destination HotSpot user %s", username)
        except Exception:
            logger.critical(
                "Destination HotSpot user rollback failed for %s", username, exc_info=True
            )

    def _restore_source_after_database_failure(
        self,
        source_client: HostelTransferRouterClient,
        destination_client: HostelTransferRouterClient,
        settled_user: dict[str, str],
        byte_limits: dict[str, int | None],
    ) -> None:
        username = str(settled_user.get("name") or "")
        self._remove_destination_copy(destination_client, username)
        try:
            source_client.create_hotspot_user_copy(settled_user, byte_limits=byte_limits)
        except Exception:
            logger.critical("Could not restore source HotSpot user %s", username, exc_info=True)


def _remaining_byte_limits(user: dict[str, str]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for limit_field, counter_field in _BYTE_LIMIT_FIELDS.items():
        limit = _router_int(user.get(limit_field))
        if limit <= 0:
            result[limit_field] = None
            continue
        if counter_field == "bytes-total":
            used = _router_int(user.get("bytes-in")) + _router_int(user.get("bytes-out"))
        else:
            used = _router_int(user.get(counter_field))
        result[limit_field] = max(0, limit - used)
    return result


def _copy_matches(
    source: dict[str, str],
    destination: dict[str, str],
    byte_limits: dict[str, int | None],
) -> bool:
    for field in ("name", "password", "profile", "comment", "disabled"):
        if str(destination.get(field) or "") != str(source.get(field) or ""):
            return False
    for field, remaining in byte_limits.items():
        expected = 0 if remaining is None else max(1, remaining)
        if _router_int(destination.get(field)) != expected:
            return False
    return True


def _router_int(value: object) -> int:
    try:
        return max(0, int(str(value or "0")))
    except (TypeError, ValueError):
        return 0
