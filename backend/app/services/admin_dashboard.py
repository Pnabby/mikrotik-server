from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import RouterDefinition
from app.models.customer import Customer
from app.models.enums import AccountStatus, PaymentStatus, SubscriptionStatus
from app.models.package import Package
from app.models.router import Router
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.admin_dashboard import (
    AdminDashboardResponse,
    DashboardRevenue,
    DashboardRouterStatus,
    DashboardTransaction,
)


def active_identity_sets(
    router_id: str, sessions: list[dict[str, str]]
) -> tuple[set[str], set[tuple[str, str, str]]]:
    """Deduplicate live users globally and devices within their router/user scope."""
    usernames = {
        str(item.get("user", "")).strip().casefold()
        for item in sessions
        if str(item.get("user", "")).strip()
    }
    device_keys = {
        (
            router_id,
            str(item.get("user", "")).strip().casefold(),
            str(item.get("mac-address") or item.get(".id") or item.get("address") or index),
        )
        for index, item in enumerate(sessions)
        if str(item.get("user", "")).strip()
    }
    return usernames, device_keys


class AdminDashboardService:
    """Build a database summary enriched with live, failure-isolated router data."""

    def __init__(self, session: Session):
        self.session = session

    def summary(self, router_id: str | None = None) -> AdminDashboardResponse:
        now = datetime.now(UTC)
        routers = self._routers(router_id)
        router_ids = [router.id for router in routers]

        live_statuses: list[DashboardRouterStatus] = []
        active_usernames: set[str] = set()
        active_device_keys: set[tuple[str, str, str]] = set()
        if routers:
            with ThreadPoolExecutor(max_workers=min(8, len(routers))) as executor:
                live_results = list(executor.map(self._live_router_status, routers))
        else:
            live_results = []
        for status, usernames, device_keys in live_results:
            live_statuses.append(status)
            active_usernames.update(usernames)
            active_device_keys.update(device_keys)

        customer_filter = Customer.router_id.in_(router_ids)
        subscription_filter = Subscription.router_id.in_(router_ids)
        transaction_filter = Transaction.router_id.in_(router_ids)

        total_users = self.session.scalar(
            select(func.count(Customer.id)).where(customer_filter)
        ) or 0
        active_account_users = self.session.scalar(
            select(func.count(Customer.id)).where(
                customer_filter,
                Customer.account_status == AccountStatus.ACTIVE,
            )
        ) or 0
        active_subscriptions = self.session.scalar(
            select(func.count(Subscription.id)).where(
                subscription_filter,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        ) or 0

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)

        return AdminDashboardResponse(
            generated_at=now,
            router_id=router_id,
            total_users=total_users,
            active_account_users=active_account_users,
            active_users=len(active_usernames),
            active_devices=len(active_device_keys),
            active_subscriptions=active_subscriptions,
            revenue=DashboardRevenue(
                today=self._revenue(transaction_filter, today_start),
                month=self._revenue(transaction_filter, month_start),
                all_time=self._revenue(transaction_filter),
                successful_payments_today=self._payment_count(
                    transaction_filter, PaymentStatus.SUCCESS, today_start
                ),
                successful_payments_month=self._payment_count(
                    transaction_filter, PaymentStatus.SUCCESS, month_start
                ),
                pending_payments=self._payment_count(
                    transaction_filter, PaymentStatus.PENDING
                ),
            ),
            routers=live_statuses,
            recent_transactions=self._recent_transactions(transaction_filter),
        )

    def _routers(self, router_id: str | None) -> list[Router]:
        query = select(Router).order_by(Router.display_order, Router.name, Router.id)
        if router_id is not None:
            query = query.where(Router.id == router_id)
        else:
            query = query.where(Router.is_active.is_(True))
        return list(self.session.scalars(query).all())

    @staticmethod
    def _definition(router: Router) -> RouterDefinition:
        return RouterDefinition(
            router_id=router.id,
            name=router.name,
            host=router.vpn_host,
            port=router.api_port,
            hotspot_network=router.hotspot_network or "",
        )

    def _live_router_status(
        self, router: Router
    ) -> tuple[DashboardRouterStatus, set[str], set[tuple[str, str, str]]]:
        if not router.is_active or not router.hotspot_network:
            return (
                DashboardRouterStatus(
                    router_id=router.id,
                    name=router.name,
                    reachable=False,
                    active_users=0,
                    active_devices=0,
                    error="Hostel is inactive or not fully configured.",
                ),
                set(),
                set(),
            )

        try:
            with mikrotik_client_context(self._definition(router)) as client:
                sessions = client.get_hotspot_active_sessions()
        except HTTPException:
            return (
                DashboardRouterStatus(
                    router_id=router.id,
                    name=router.name,
                    reachable=False,
                    active_users=0,
                    active_devices=0,
                    error="Router could not be reached.",
                ),
                set(),
                set(),
            )

        usernames, device_keys = active_identity_sets(router.id, sessions)
        return (
            DashboardRouterStatus(
                router_id=router.id,
                name=router.name,
                reachable=True,
                active_users=len(usernames),
                active_devices=len(device_keys),
            ),
            usernames,
            device_keys,
        )

    def _revenue(self, scope_filter, since: datetime | None = None) -> dict[str, Decimal]:
        query = (
            select(Transaction.currency, func.sum(Transaction.amount))
            .where(
                scope_filter,
                Transaction.payment_status == PaymentStatus.SUCCESS,
            )
            .group_by(Transaction.currency)
        )
        if since is not None:
            query = query.where(Transaction.paid_at >= since)
        return {currency: amount or Decimal(0) for currency, amount in self.session.execute(query)}

    def _payment_count(
        self,
        scope_filter,
        payment_status: PaymentStatus,
        since: datetime | None = None,
    ) -> int:
        query = select(func.count(Transaction.id)).where(
            scope_filter,
            Transaction.payment_status == payment_status,
        )
        if since is not None:
            query = query.where(Transaction.paid_at >= since)
        return self.session.scalar(query) or 0

    def _recent_transactions(self, scope_filter) -> list[DashboardTransaction]:
        query = (
            select(Transaction, Customer.username, Package.name)
            .join(Customer, Transaction.customer_id == Customer.id)
            .join(Package, Transaction.package_id == Package.id)
            .where(scope_filter)
            .order_by(func.coalesce(Transaction.paid_at, Transaction.created_at).desc())
            .limit(6)
        )
        return [
            DashboardTransaction(
                reference=transaction.paystack_reference,
                customer=username,
                package=package_name,
                amount=transaction.amount,
                currency=transaction.currency,
                status=transaction.payment_status,
                occurred_at=transaction.paid_at or transaction.created_at,
            )
            for transaction, username, package_name in self.session.execute(query)
        ]
