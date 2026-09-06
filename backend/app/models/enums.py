from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum


class AccountStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class RouterStatus(StrEnum):
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class OtpPurpose(StrEnum):
    REGISTRATION = "registration"
    USERNAME_RECOVERY = "username_recovery"
    PIN_RESET = "pin_reset"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class PaymentEventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


class ActivationStatus(StrEnum):
    NOT_STARTED = "not_started"
    PROCESSING = "processing"
    PROVISIONING = "provisioning"
    RETRY_REQUIRED = "retry_required"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    SUCCESS = "success"
    MANUAL_REVIEW = "manual_review"
    SUPERSEDED = "superseded"


class ActivationTrigger(StrEnum):
    PAYMENT_VERIFICATION = "payment_verification"
    PAYSTACK_WEBHOOK = "paystack_webhook"
    CUSTOMER_RETRY = "customer_retry"
    SCHEDULED_RECONCILIATION = "scheduled_reconciliation"
    ADMIN_RETRY = "admin_retry"


class ActivationAttemptOutcome(StrEnum):
    PROCESSING = "processing"
    SUCCESS = "success"
    RETRY_REQUIRED = "retry_required"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    MANUAL_REVIEW = "manual_review"
    SUPERSEDED = "superseded"


class SubscriptionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class AdminRole(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMINISTRATOR = "administrator"


class AuditActorType(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    SYSTEM = "system"


def enum_type(enum_class: type[StrEnum], name: str) -> Enum:
    """Create evolvable string-backed enums with database check constraints."""

    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
