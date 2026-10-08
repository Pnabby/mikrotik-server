"""Operator inspection/retry: python -m app.commands.recover_hostel_transfers."""

import argparse
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.hostel_transfer import HostelTransferOperation
from app.services.hostel_transfer_reconciliation import reconcile_hostel_transfers


def main():
    parser = argparse.ArgumentParser(
        description="Inspect or safely reconcile pending hostel transfers."
    )
    parser.add_argument("--operation-id", type=uuid.UUID)
    parser.add_argument("--reconcile", action="store_true", help="Retry pending operations.")
    parser.add_argument(
        "--retry-manual",
        action="store_true",
        help="Re-check a specific manual-review operation after operator investigation.",
    )
    args = parser.parse_args()
    if args.retry_manual and (not args.reconcile or args.operation_id is None):
        parser.error("--retry-manual requires --reconcile and --operation-id")
    if args.reconcile:
        count = reconcile_hostel_transfers(
            get_settings(), operation_id=args.operation_id, retry_manual=args.retry_manual
        )
        print(json.dumps({"recovered": count}))
    with Session(get_engine()) as session:
        query = select(HostelTransferOperation).where(HostelTransferOperation.is_active.is_(True))
        if args.operation_id:
            query = query.where(HostelTransferOperation.id == args.operation_id)
        for operation in session.scalars(query.order_by(HostelTransferOperation.created_at)):
            print(
                json.dumps(
                    {
                        "operation_id": str(operation.id),
                        "customer_id": str(operation.customer_id),
                        "source_router_id": operation.source_router_id,
                        "destination_router_id": operation.destination_router_id,
                        "status": operation.status,
                        "stage": operation.stage,
                        "reason": operation.error_code,
                        "attempts": operation.attempt_count,
                        "next_retry_at": str(operation.next_retry_at),
                    }
                )
            )


if __name__ == "__main__":
    main()
