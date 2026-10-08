"""Durable transfer checkpoints and conservative, repeatable recovery.

Snapshots precede router mutations. Existing accounts only change their temporary
ownership marker/disabled flag; allowances and counters are never reset in place.
"""

import logging
from datetime import UTC, datetime, timedelta

from cryptography.fernet import InvalidToken
from fastapi import status
from routeros_api.exceptions import RouterOsApiError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.client import _HOTSPOT_USER_TRANSFER_FIELDS, _parse_routeros_duration
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import AuditActorType, SubscriptionStatus
from app.models.hostel_transfer import HostelTransferOperation
from app.models.subscription import Subscription
from app.services.hostel_transfer_availability import check_transfer_routers, router_failure_reason

logger = logging.getLogger(__name__)


class ManualTransferReview(Exception):
    """Carries only a fixed reason code, never a RouterOS account or password."""


def _disabled(value):
    return str(value).lower() in {"true", "yes", "1"}


def _same_settings(expected, actual):
    if actual is None:
        return False
    defaults = {
        "server": "all",
        "address": "0.0.0.0",
        "mac-address": "00:00:00:00:00:00",
        "limit-uptime": "0s",
        "limit-bytes-in": "0",
        "limit-bytes-out": "0",
        "limit-bytes-total": "0",
        "disabled": "no",
    }
    for field in _HOTSPOT_USER_TRANSFER_FIELDS:
        left = expected.get(field, defaults.get(field, ""))
        right = actual.get(field, defaults.get(field, ""))
        if field == "disabled":
            if _disabled(left) != _disabled(right):
                return False
        elif field == "limit-uptime":
            if _parse_routeros_duration(left) != _parse_routeros_duration(right):
                return False
        elif str(left or "") != str(right or ""):
            return False
    return True


def _marker(operation, role, comment):
    return f"{comment or ''};hostel-transfer={operation.id}:{role}"


def _final_settings_match(expected, actual):
    if _same_settings(expected, actual):
        return True
    if actual is None:
        return False
    original_comment = expected.get("comment") or ""
    if any(
        part.partition("=")[0].strip().lower() == "login" for part in original_comment.split(";")
    ):
        return False
    # A never-used account can log in immediately after enabling. Accept only
    # that first appended login timestamp, without overwriting it or any limits.
    comment = actual.get("comment") or ""
    prefix = original_comment + ";" if original_comment else ""
    suffix = comment.removeprefix(prefix)
    from app.services.hotspot import _parse_login_datetime

    return (
        comment.startswith(prefix)
        and suffix.startswith("login=")
        and ";" not in suffix
        and _parse_login_datetime(suffix) is not None
        and _same_settings({**expected, "comment": comment}, actual)
    )


def _state(user):
    if user is None:
        return {"present": False}
    return {
        "present": True,
        "id": user.get("id"),
        "disabled": _disabled(user.get("disabled")),
        "bytes_in": user.get("bytes-in", "0"),
        "bytes_out": user.get("bytes-out", "0"),
        "uptime": user.get("uptime", "0s"),
    }


class HostelTransferRecovery:
    def __init__(self, session, cipher):
        self.session = session
        self.cipher = cipher

    def run(self, operation, source, destination, *, raise_errors=True, routers_checked=False):
        operation_id = operation.id
        try:
            if not operation.is_active:
                return operation
            if operation.status == "manual_review":
                raise ManualTransferReview(operation.error_code or "manual_review")
            operation.attempt_count += 1
            self._checkpoint(operation, operation.stage)
            if not routers_checked:
                check_transfer_routers(source, destination)
            snapshot = self.cipher.decrypt(operation.id, operation.encrypted_snapshot)
            self._drive(operation, snapshot, source, destination)
            return operation
        except (InvalidToken, KeyError, ValueError, ManualTransferReview) as exc:
            code = str(exc) if isinstance(exc, ManualTransferReview) else "snapshot_invalid"
            self.record_failure(operation_id, code, manual=True)
            if raise_errors:
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "Transfer requires reconciliation.",
                    error_code="hostel_transfer_unconfirmed",
                ) from None
        except SQLAlchemyError:
            # Commit may have succeeded remotely. Do not compensate using an
            # in-memory customer or stale stage: the next pass reads the journal.
            self.record_failure(operation_id, "database_unavailable")
            if raise_errors:
                raise ServiceError(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "Transfer will be reconciled when the database is available.",
                    error_code="hostel_transfer_unconfirmed",
                ) from None
        except ServiceError as exc:
            # A recovery preflight can fail before either account is touched.
            # Retain the journal and its direction, then retry when both APIs work.
            self.record_failure(operation_id, exc.error_code or "router_preflight_failed")
            if raise_errors:
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "Transfer requires reconciliation.",
                    error_code="hostel_transfer_unconfirmed",
                ) from None
        except (OSError, RouterOsApiError) as exc:
            self.record_failure(operation_id, f"router_{router_failure_reason(exc)}", rollback=True)
            if raise_errors:
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "Transfer requires reconciliation.",
                    error_code="hostel_transfer_unconfirmed",
                ) from None
        except Exception:  # noqa: BLE001 - Unexpected adapter failures must remain recoverable.
            self.record_failure(operation_id, "router_operation_unconfirmed", rollback=True)
            if raise_errors:
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY,
                    "Transfer requires reconciliation.",
                    error_code="hostel_transfer_unconfirmed",
                ) from None
        return None

    def record_failure(self, operation_id, code, *, manual=False, rollback=False):
        try:
            self.session.rollback()
            operation = self.session.get(
                HostelTransferOperation, operation_id, populate_existing=True
            )
            if operation is None or not operation.is_active:
                return
            if operation.status == "manual_review" and not manual:
                # A later transport/disconnect failure must not turn an
                # ambiguous account into an automatic retry.
                return
            operation.status = "manual_review" if manual else "reconciliation_required"
            operation.error_code = code
            if rollback:
                operation.last_confirmed_state = {
                    **operation.last_confirmed_state,
                    "rollback_requested": True,
                }
            operation.next_retry_at = (
                None
                if manual
                else datetime.now(UTC)
                + timedelta(seconds=min(3600, 30 * 2 ** min(operation.attempt_count, 7)))
            )
            self.session.commit()
        except SQLAlchemyError:
            self.session.rollback()
            # The last committed intent and encrypted snapshot remain recoverable.
        logger.warning(
            "Hostel transfer needs recovery: operation_id=%s reason=%s", operation_id, code
        )

    def _checkpoint(self, operation, stage, *, snapshot=None):
        operation.stage = stage
        operation.status = "running"
        operation.error_code = None
        operation.next_retry_at = None
        if snapshot is not None:
            operation.encrypted_snapshot = self.cipher.encrypt(operation.id, snapshot)
        self.session.add(operation)
        self.session.commit()

    def _observe(self, operation, source, destination):
        operation.last_confirmed_state = {
            **operation.last_confirmed_state,
            "source": _state(source),
            "destination": _state(destination),
            "observed_at": datetime.now(UTC).isoformat(),
        }

    def _drive(self, operation, snapshot, source_client, destination_client):
        if not isinstance(snapshot.get("original"), dict):
            raise ManualTransferReview("snapshot_invalid")
        original = snapshot["original"]
        claimed_source = {
            **original,
            "comment": _marker(operation, "source", original.get("comment")),
            "disabled": "yes",
        }
        source = source_client.get_hotspot_user(operation.username)
        destination = destination_client.get_hotspot_user(operation.username)
        self._observe(operation, source, destination)
        customer = self.session.scalar(
            select(Customer)
            .where(Customer.id == operation.customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if customer is None or customer.router_id not in {
            operation.source_router_id,
            operation.destination_router_id,
        }:
            raise ManualTransferReview("customer_changed")

        # Before settlement, only the recorded original or our frozen source can
        # be touched. A failed/uncertain claim can be rolled back without quotas.
        if "transfer" not in snapshot:
            if destination is not None or source is None:
                raise ManualTransferReview("unexpected_router_state_before_settlement")
            if source.get("id") != operation.source_user_id:
                raise ManualTransferReview("source_identity_changed")
            if _same_settings(original, source):
                if operation.last_confirmed_state.get("rollback_requested"):
                    self._terminal(operation, "rolled_back")
                    return
                self._checkpoint(operation, "claiming_source")
                source = source_client.mutate_hotspot_transfer_user(
                    source,
                    comment=claimed_source["comment"],
                    disabled=True,
                )
            if not _same_settings(claimed_source, source):
                raise ManualTransferReview("source_changed")
            self._checkpoint(operation, "settling_usage")
            settled = source_client.settle_hotspot_transfer_user(source)
            if not _same_settings(claimed_source, settled):
                raise ManualTransferReview("source_changed_during_settlement")
            # Preserve the original disabled state and original login= timestamp.
            settled = {
                **settled,
                "comment": original.get("comment", ""),
                "disabled": original.get("disabled", "no"),
            }
            from app.services.hostel_transfer import (
                _remaining_byte_limits,
                _user_with_remaining_uptime,
            )

            limits = _remaining_byte_limits(settled)
            restored = _user_with_remaining_uptime(settled)
            transfer = {**restored, "server": "all"}
            transfer.pop("address", None)
            transfer.pop("routes", None)
            if any(remaining == 0 for remaining in limits.values()):
                transfer["disabled"] = "yes"
            for field, remaining in limits.items():
                transfer[field] = str(0 if remaining is None else max(1, remaining))
            snapshot = {**snapshot, "settled": settled, "transfer": transfer}
            operation.remaining_byte_limits = limits
            operation.remaining_uptime_seconds = (
                max(
                    0,
                    _parse_routeros_duration(original.get("limit-uptime"))
                    - _parse_routeros_duration(settled.get("uptime")),
                )
                if _parse_routeros_duration(original.get("limit-uptime"))
                else None
            )
            self._checkpoint(operation, "settled", snapshot=snapshot)
            source = source_client.get_hotspot_user(operation.username)

        final = snapshot["transfer"]
        staged = {
            **final,
            "comment": _marker(operation, "destination", final.get("comment")),
            "disabled": "yes",
        }
        if source is not None and (
            source.get("id") != operation.source_user_id
            or not _same_settings(claimed_source, source)
        ):
            # A completed rollback can lose its DB acknowledgement too.
            if (
                operation.last_confirmed_state.get("rollback_requested")
                and destination is None
                and customer.router_id == operation.source_router_id
                and source.get("id") == operation.source_user_id
                and _same_settings(original, source)
            ):
                self._terminal(operation, "rolled_back")
                return
            raise ManualTransferReview("source_changed")

        if destination is not None:
            if (
                operation.destination_user_id
                and destination.get("id") != operation.destination_user_id
            ):
                raise ManualTransferReview("destination_identity_changed")
            if (
                customer.router_id == operation.destination_router_id
                and source is None
                and operation.destination_user_id == destination.get("id")
                and _final_settings_match(final, destination)
            ):
                # Final enable/marker removal reached RouterOS before a crash.
                self._terminal(operation, "completed")
                return
            if not _same_settings(staged, destination):
                raise ManualTransferReview("destination_changed")
            if _used(destination):
                raise ManualTransferReview("staged_destination_has_usage")
        elif source is None or customer.router_id == operation.destination_router_id:
            raise ManualTransferReview("destination_missing_after_source_removal")

        if operation.last_confirmed_state.get("rollback_requested") and source is not None:
            if customer.router_id != operation.source_router_id:
                raise ManualTransferReview("source_reappeared_after_commit")
            self._rollback(
                operation, original, source, destination, source_client, destination_client
            )
            return

        if source is not None and not _same_usage(snapshot["settled"], source):
            raise ManualTransferReview("source_usage_changed_after_settlement")

        if destination is None:
            self._checkpoint(operation, "creating_destination")
            destination = destination_client.create_hotspot_user_copy(
                staged,
                byte_limits=operation.remaining_byte_limits,
            )
            if not _same_settings(staged, destination) or not destination.get("id"):
                raise ManualTransferReview("destination_verification_failed")
        operation.destination_user_id = destination["id"]
        self._observe(operation, source, destination)
        self._checkpoint(operation, "destination_verified")

        if source is not None:
            if customer.router_id != operation.source_router_id:
                raise ManualTransferReview("source_reappeared_after_commit")
            self._checkpoint(operation, "removing_source")
            source = source_client.mutate_hotspot_transfer_user(source, remove=True)
            if source is not None:
                raise RuntimeError("Source removal was not confirmed.")
        self._observe(operation, source, destination)
        self._checkpoint(operation, "source_removed")

        # This commit changes only router ownership, exactly as the existing
        # successful path did. Subscription allowance and dates remain untouched.
        if customer.router_id == operation.source_router_id:
            self._checkpoint(operation, "committing_database")
            customer = self.session.scalar(
                select(Customer)
                .where(Customer.id == operation.customer_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if customer is None or customer.router_id != operation.source_router_id:
                raise ManualTransferReview("customer_changed")
            subscriptions = list(
                self.session.scalars(
                    select(Subscription)
                    .where(
                        Subscription.customer_id == customer.id,
                        Subscription.status == SubscriptionStatus.ACTIVE,
                    )
                    .with_for_update()
                )
            )
            if {str(sub.id) for sub in subscriptions} != set(operation.subscription_ids):
                raise ManualTransferReview("subscriptions_changed")
            customer.router_id = operation.destination_router_id
            for subscription in subscriptions:
                subscription.router_id = operation.destination_router_id
            self.session.add(
                AuditLog(
                    actor_type=AuditActorType(operation.actor_type),
                    admin_user_id=operation.admin_user_id,
                    customer_id=customer.id,
                    action="customer.hostel_transferred",
                    entity_type="customer",
                    entity_id=str(customer.id),
                    ip_address=operation.ip_address,
                    details={
                        "username": operation.username,
                        "source_router_id": operation.source_router_id,
                        "destination_router_id": operation.destination_router_id,
                        "remaining_data_limit_bytes": operation.remaining_byte_limits[
                            "limit-bytes-total"
                        ],
                        "transfer_operation_id": str(operation.id),
                    },
                )
            )
            operation.stage = "database_committed"
            self.session.commit()

        # Last write: make the sole destination usable and restore its exact
        # original comment (including login=). No counters/limits are changed.
        destination = destination_client.get_hotspot_user(operation.username)
        if (
            destination is None
            or destination.get("id") != operation.destination_user_id
            or not _same_settings(staged, destination)
        ):
            raise ManualTransferReview("destination_changed_before_enable")
        self._checkpoint(operation, "enabling_destination")
        destination = destination_client.mutate_hotspot_transfer_user(
            destination,
            comment=final.get("comment", ""),
            disabled=_disabled(final.get("disabled")),
        )
        if not _final_settings_match(final, destination):
            raise ManualTransferReview("destination_enable_unconfirmed")
        self._observe(operation, None, destination)
        self._terminal(operation, "completed")

    def _rollback(
        self, operation, original, source, destination, source_client, destination_client
    ):
        # Both accounts were read successfully, and the source is frozen/owned.
        # Remove only a matching disabled destination, then restore source flags.
        self._checkpoint(operation, "rolling_back")
        if destination is not None:
            destination = destination_client.mutate_hotspot_transfer_user(destination, remove=True)
            if destination is not None:
                raise RuntimeError("Destination cleanup was not confirmed.")
        source = source_client.mutate_hotspot_transfer_user(
            source,
            comment=original.get("comment", ""),
            disabled=_disabled(original.get("disabled")),
        )
        if not _same_settings(original, source):
            raise ManualTransferReview("source_restore_unconfirmed")
        self._observe(operation, source, None)
        self._terminal(operation, "rolled_back")

    def _terminal(self, operation, result):
        operation.status = result
        operation.stage = result
        operation.is_active = False
        operation.completed_at = datetime.now(UTC)
        operation.next_retry_at = None
        operation.error_code = None
        # Drop credential-bearing snapshots once recovery is no longer needed.
        operation.encrypted_snapshot = None
        self.session.commit()


def _used(user):
    return any(int(user.get(field) or 0) > 0 for field in ("bytes-in", "bytes-out")) or bool(
        _parse_routeros_duration(user.get("uptime"))
    )


def _same_usage(expected, actual):
    return all(
        int(expected.get(field) or 0) == int(actual.get(field) or 0)
        for field in ("bytes-in", "bytes-out")
    ) and _parse_routeros_duration(expected.get("uptime")) == _parse_routeros_duration(
        actual.get("uptime")
    )
