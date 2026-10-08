from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ServiceError
from app.core.security import PasswordHasher, PinHasher
from app.core.transfer_security import TransferSnapshotCipher
from app.integrations.mikrotik.client import _HOTSPOT_USER_TRANSFER_FIELDS, _parse_routeros_duration
from app.models.activation import Activation
from app.models.admin_user import AdminUser
from app.models.customer import Customer
from app.models.enums import ActivationStatus, AuditActorType, PaymentStatus, SubscriptionStatus
from app.models.hostel_transfer import HostelTransferOperation
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services.hostel_transfer_availability import check_transfer_routers, transfer_router_read
from app.services.hostel_transfer_recovery import HostelTransferRecovery
from app.services.profile_settings import profile_differences
from app.services.transfer_lock import transfer_lock

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
    def check_transfer_availability(self) -> None: ...

    def get_hotspot_user(self, username: str) -> dict[str, str] | None: ...

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None: ...

    def clear_hotspot_authentication(self, username: str) -> dict[str, str] | None: ...

    def create_hotspot_user_copy(
        self,
        user: dict[str, str],
        *,
        byte_limits: dict[str, int | None],
    ) -> dict[str, str]: ...

    def mutate_hotspot_transfer_user(
        self,
        expected: dict[str, str],
        *,
        comment=None,
        disabled=None,
        remove=False,
    ) -> dict[str, str] | None: ...

    def settle_hotspot_transfer_user(self, expected: dict[str, str]) -> dict[str, str] | None: ...


@dataclass(frozen=True, slots=True)
class HostelTransferResult:
    router_id: str
    router_name: str
    remaining_data_limit_bytes: int | None


class HostelTransferService:
    def __init__(self, session: Session, *, cipher: TransferSnapshotCipher | None = None) -> None:
        self._session = session
        self._cipher = cipher

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
        **kwargs,
    ) -> HostelTransferResult:
        with transfer_lock(self._session, customer.id):
            try:
                pending = self._session.scalar(
                    select(HostelTransferOperation.id).where(
                        HostelTransferOperation.customer_id == customer.id,
                        HostelTransferOperation.is_active.is_(True),
                    )
                )
            except SQLAlchemyError:
                self._session.rollback()
                raise ServiceError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Transfer storage is unavailable.",
                    error_code="hostel_transfer_storage_unavailable",
                ) from None
            if pending is not None:
                raise ServiceError(
                    status.HTTP_409_CONFLICT,
                    "A hostel transfer is pending recovery.",
                    error_code="hostel_transfer_in_progress",
                )
            return self._start_transfer(customer, **kwargs)

    def _start_transfer(
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
            select(Customer)
            .where(Customer.id == customer.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_customer is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Customer was not found.")
        customer = locked_customer
        source_router_id = customer.router_id
        if destination_router_id == source_router_id:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The customer is already at this hostel.",
                error_code="hostel_already_selected",
            )
        unresolved_activation = next(
            iter(
                self._session.scalars(
                    select(Activation.id).join(
                        Transaction, Activation.transaction_id == Transaction.id,
                    ).where(
                        Activation.customer_id == customer.id,
                        Activation.status.in_(_UNRESOLVED_ACTIVATION_STATUSES),
                        # Checkout creates a NOT_STARTED activation before payment.
                        # An unpaid, never-attempted checkout has no router work to
                        # settle; paid or possibly applied activations still block.
                        or_(
                            Transaction.payment_status == PaymentStatus.SUCCESS,
                            Activation.status != ActivationStatus.NOT_STARTED,
                            Activation.attempt_count > 0,
                        ),
                    )
                )
            ),
            None,
        )
        if unresolved_activation is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Finish the pending plan activation before changing hostels.",
                error_code="hostel_activation_pending",
            )

        check_transfer_routers(source_client, destination_client)
        source_user = transfer_router_read(
            "source", lambda: source_client.get_hotspot_user(customer.username)
        )
        if source_user is None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The source network account is missing.",
                error_code="hostel_source_user_missing",
            )
        if transfer_router_read(
            "destination", lambda: destination_client.get_hotspot_user(customer.username)
        ) is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "That username already exists at the destination hostel.",
                error_code="hostel_username_conflict",
            )
        profile = str(source_user.get("profile") or "").strip()
        destination_profile = (
            transfer_router_read(
                "destination", lambda: destination_client.get_hotspot_user_profile(profile)
            ) if profile else None
        )
        if destination_profile is None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The customer's network profile is unavailable at the destination hostel.",
                error_code="hostel_profile_missing",
            )
        source_profile = transfer_router_read(
            "source", lambda: source_client.get_hotspot_user_profile(profile)
        )
        if source_profile is None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The source profile is missing.",
                error_code="hostel_profile_missing",
            )
        if profile_differences(source_profile, destination_profile):
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The hostel profiles have different network settings.",
                error_code="hostel_profile_mismatch",
            )

        if not source_user.get("id"):
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "Source account identity is unconfirmed.",
                error_code="hostel_transfer_unconfirmed",
            )
        try:
            cipher = self._cipher or TransferSnapshotCipher.from_settings(get_settings())
        except ValueError:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Transfer recovery is not configured.",
                error_code="hostel_transfer_not_configured",
            ) from None
        operation_id = uuid4()
        operation = HostelTransferOperation(
            id=operation_id,
            customer_id=customer.id,
            username=customer.username,
            source_router_id=source_router_id,
            destination_router_id=destination_router_id,
            destination_router_name=destination_router_name,
            source_user_id=source_user["id"],
            actor_type=actor_type.value,
            admin_user_id=admin.id if admin else None,
            ip_address=(ip_address or "")[:64] or None,
            encrypted_snapshot=cipher.encrypt(
                operation_id,
                {
                    "original": {
                        key: value
                        for key, value in source_user.items()
                        if key
                        in set(_HOTSPOT_USER_TRANSFER_FIELDS)
                        | {"id", "bytes-in", "bytes-out", "uptime"}
                    }
                },
            ),
            subscription_ids=[
                str(value)
                for value in self._session.scalars(
                    select(Subscription.id).where(
                        Subscription.customer_id == customer.id,
                        Subscription.status == SubscriptionStatus.ACTIVE,
                    )
                )
            ],
        )
        self._session.add(operation)
        try:
            # No router mutation is permitted until recovery data is durable.
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A hostel transfer is already pending.",
                error_code="hostel_transfer_in_progress",
            ) from None
        except SQLAlchemyError:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Transfer could not be recorded. Please try again.",
                error_code="hostel_transfer_storage_unavailable",
            ) from None
        HostelTransferRecovery(self._session, cipher).run(
            operation, source_client, destination_client, routers_checked=True
        )
        if operation.status != "completed":
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "Transfer was safely rolled back.",
                error_code="hostel_transfer_unconfirmed",
            )
        return HostelTransferResult(
            router_id=operation.destination_router_id,
            router_name=operation.destination_router_name,
            remaining_data_limit_bytes=operation.remaining_byte_limits["limit-bytes-total"],
        )


def _user_with_remaining_uptime(user: dict[str, str]) -> dict[str, str]:
    result = dict(user)
    limit = _parse_routeros_duration(user.get("limit-uptime"))
    if limit:
        remaining = max(0, limit - _parse_routeros_duration(user.get("uptime")))
        result["limit-uptime"] = f"{max(1, remaining)}s"
        if remaining == 0:
            result["disabled"] = "yes"
    return result


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
    if source.get("server") and destination.get("server") != source["server"]:
        return False
    if _parse_routeros_duration(source.get("limit-uptime")) != _parse_routeros_duration(
        destination.get("limit-uptime")
    ):
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
