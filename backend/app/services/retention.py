from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.db.session import get_engine
from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.models.customer import Customer
from app.models.enums import SubscriptionStatus
from app.models.router import Router
from app.models.subscription import Subscription
from app.services.account_deletion import AccountDeletionService

logger = logging.getLogger(__name__)


def _inactive_customer_filter(cutoff: datetime):
    has_live_plan = exists(
        select(Subscription.id).where(
            Subscription.customer_id == Customer.id,
            Subscription.status.in_(
                (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE)
            ),
        )
    )
    return Customer.last_activity_at < cutoff, ~has_live_plan


def delete_inactive_accounts(settings: Settings, *, batch_size: int = 100) -> int:
    """Erase inactive customers past retention once no live paid plan remains."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.inactive_account_retention_days)
    session_factory = sessionmaker(
        bind=get_engine(), autoflush=False, expire_on_commit=False
    )
    with session_factory() as lookup_session:
        candidate_ids = list(
            lookup_session.scalars(
                select(Customer.id)
                .join(Router, Router.id == Customer.router_id)
                .where(Router.is_active.is_(True), *_inactive_customer_filter(cutoff))
                .order_by(Customer.last_activity_at)
                .limit(batch_size)
            )
        )

    deleted_count = 0
    for customer_id in candidate_ids:
        with session_factory() as session:
            customer = session.scalar(
                select(Customer)
                .where(
                    Customer.id == customer_id,
                    *_inactive_customer_filter(cutoff),
                )
                .with_for_update()
            )
            if customer is None:
                continue
            try:
                router_definition = get_router(session, customer.router_id)
                with mikrotik_client_context(router_definition) as client:
                    AccountDeletionService(session).erase(customer, client)
            except (ServiceError, UnknownRouterError):
                session.rollback()
                logger.exception(
                    "Inactive account cleanup will retry; customer_id=%s", customer_id
                )
                continue
            deleted_count += 1
    return deleted_count
