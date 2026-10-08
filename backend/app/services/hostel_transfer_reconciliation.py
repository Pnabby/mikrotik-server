"""Restart recovery using the same journal and customer lock as HTTP transfers."""

import logging
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ServiceError
from app.core.transfer_security import TransferSnapshotCipher
from app.db.session import get_engine
from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import get_router
from app.models.hostel_transfer import HostelTransferOperation
from app.services.hostel_transfer_recovery import HostelTransferRecovery
from app.services.transfer_lock import transfer_lock

logger = logging.getLogger(__name__)


def reconcile_hostel_transfers(
    settings,
    *,
    session_factory=None,
    client_context=None,
    operation_id=None,
    retry_manual=False,
    batch_size=50,
):
    """Retry due operations; explicit operation IDs bypass backoff, never ownership checks."""
    factory = session_factory or sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )
    context = client_context or mikrotik_client_context
    cipher = TransferSnapshotCipher.from_settings(settings)
    with factory() as session:
        query = select(HostelTransferOperation.id).where(
            HostelTransferOperation.is_active.is_(True)
        )
        if operation_id is not None:
            query = query.where(HostelTransferOperation.id == operation_id)
        else:
            query = query.where(
                or_(
                    HostelTransferOperation.next_retry_at.is_(None),
                    HostelTransferOperation.next_retry_at <= datetime.now(UTC),
                )
            )
        if not retry_manual:
            query = query.where(HostelTransferOperation.status != "manual_review")
        ids = list(
            session.scalars(query.order_by(HostelTransferOperation.created_at).limit(batch_size))
        )

    completed = 0
    for transfer_id in ids:
        with factory() as session:
            operation = session.get(HostelTransferOperation, transfer_id)
            if operation is None or not operation.is_active:
                continue
            recovery = HostelTransferRecovery(session, cipher)
            try:
                with transfer_lock(session, operation.customer_id):
                    session.refresh(operation)
                    if not operation.is_active or (
                        operation.status == "manual_review" and not retry_manual
                    ):
                        continue
                    if retry_manual and operation.status == "manual_review":
                        operation.status = "reconciliation_required"
                        session.commit()
                    try:
                        source_router = get_router(session, operation.source_router_id)
                        destination_router = get_router(session, operation.destination_router_id)
                        with (
                            context(source_router) as source,
                            context(destination_router) as destination,
                        ):
                            result = recovery.run(
                                operation, source, destination, raise_errors=False
                            )
                        if result is not None and not result.is_active:
                            completed += 1
                    except Exception:  # noqa: BLE001 - RouterOS/context failures must stay recoverable.
                        recovery.record_failure(transfer_id, "router_unavailable")
            except ServiceError as exc:
                if exc.error_code != "hostel_transfer_in_progress":
                    raise
            except Exception:  # noqa: BLE001 - Continue other operations after a connection failure.
                # Do not log exception text: router failures can contain credentials.
                logger.warning(
                    "Hostel transfer reconciliation deferred: operation_id=%s", transfer_id
                )
    return completed
