from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import RouterDefinition
from app.models.customer import Customer
from app.models.enums import AccountStatus, PaymentStatus, SubscriptionStatus
from app.models.package import Package
from app.models.router import Router
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.admin_dashboard import (
    AdminConnectedDevice,
    AdminCustomerDetail,
    AdminCustomerDirectoryResponse,
    AdminDashboardResponse,
    AdminTransactionDetail,
    AdminTransactionListResponse,
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


def _optional_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


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

    def transactions(
        self,
        *,
        router_id: str | None,
        payment_status: PaymentStatus | None,
        date_from: date | None,
        date_to: date | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> AdminTransactionListResponse:
        if date_from is not None and date_to is not None and date_to < date_from:
            raise HTTPException(status_code=400, detail="End date cannot be before start date.")

        routers = self._routers(router_id)
        router_ids = [router.id for router in routers]
        conditions = [Transaction.router_id.in_(router_ids)]
        occurred_at = func.coalesce(Transaction.paid_at, Transaction.created_at)
        if payment_status is not None:
            conditions.append(Transaction.payment_status == payment_status)
        if date_from is not None:
            conditions.append(occurred_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
        if date_to is not None:
            conditions.append(
                occurred_at
                < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
            )
        normalized_search = (search or "").strip().casefold()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                or_(
                    func.lower(Transaction.paystack_reference).like(pattern),
                    func.lower(Customer.username).like(pattern),
                    func.lower(Customer.email).like(pattern),
                    func.lower(Package.name).like(pattern),
                )
            )

        base_query = (
            select(Transaction)
            .join(Customer, Transaction.customer_id == Customer.id)
            .join(Package, Transaction.package_id == Package.id)
            .options(
                joinedload(Transaction.customer),
                joinedload(Transaction.package),
                joinedload(Transaction.router),
                joinedload(Transaction.activation),
            )
            .where(*conditions)
        )
        count_query = (
            select(func.count(Transaction.id))
            .join(Customer, Transaction.customer_id == Customer.id)
            .join(Package, Transaction.package_id == Package.id)
            .where(*conditions)
        )
        total = int(self.session.scalar(count_query) or 0)
        status_counts = {
            status_value: count
            for status_value, count in self.session.execute(
                select(Transaction.payment_status, func.count(Transaction.id))
                .join(Customer, Transaction.customer_id == Customer.id)
                .join(Package, Transaction.package_id == Package.id)
                .where(*conditions)
                .group_by(Transaction.payment_status)
            )
        }
        revenue = {
            currency: amount or Decimal(0)
            for currency, amount in self.session.execute(
                select(Transaction.currency, func.sum(Transaction.amount))
                .join(Customer, Transaction.customer_id == Customer.id)
                .join(Package, Transaction.package_id == Package.id)
                .where(*conditions, Transaction.payment_status == PaymentStatus.SUCCESS)
                .group_by(Transaction.currency)
            )
        }
        transactions = self.session.scalars(
            base_query.order_by(occurred_at.desc()).offset(offset).limit(limit)
        ).all()

        return AdminTransactionListResponse(
            generated_at=datetime.now(UTC),
            total=total,
            offset=offset,
            limit=limit,
            revenue=revenue,
            successful=int(status_counts.get(PaymentStatus.SUCCESS, 0)),
            pending=int(status_counts.get(PaymentStatus.PENDING, 0)),
            failed=int(status_counts.get(PaymentStatus.FAILED, 0)),
            transactions=[
                AdminTransactionDetail(
                    reference=transaction.paystack_reference,
                    customer_username=transaction.customer.username,
                    customer_email=transaction.customer.email,
                    customer_phone=transaction.customer.phone_number,
                    hostel_id=transaction.router_id,
                    hostel_name=transaction.router.name,
                    package=transaction.package.name,
                    amount=transaction.amount,
                    currency=transaction.currency,
                    status=transaction.payment_status,
                    provider_status=transaction.provider_status,
                    activation_status=(
                        transaction.activation.status if transaction.activation else None
                    ),
                    occurred_at=transaction.paid_at or transaction.created_at,
                    paid_at=transaction.paid_at,
                )
                for transaction in transactions
            ],
        )

    def customers_and_devices(
        self,
        *,
        router_id: str | None,
        account_status: AccountStatus | None,
        subscription: str,
        search: str | None,
        limit: int,
    ) -> AdminCustomerDirectoryResponse:
        now = datetime.now(UTC)
        routers = self._routers(router_id)
        router_ids = [router.id for router in routers]
        live_results: list[tuple[DashboardRouterStatus, list[dict[str, str]]]] = []
        if routers:
            with ThreadPoolExecutor(max_workers=min(8, len(routers))) as executor:
                live_results = list(executor.map(self._live_router_sessions, routers))

        router_names = {router.id: router.name for router in routers}
        live_usernames: set[str] = set()
        device_rows: list[tuple[str, str, str, dict[str, str]]] = []
        for live_status, sessions in live_results:
            for index, item in enumerate(sessions):
                username = str(item.get("user", "")).strip()
                if not username:
                    continue
                live_usernames.add(username.casefold())
                session_id = str(
                    item.get(".id")
                    or item.get("mac-address")
                    or item.get("address")
                    or f"session-{index}"
                )
                device_rows.append((live_status.router_id, session_id, username, item))

        scope = Customer.router_id.in_(router_ids)
        conditions = [scope]
        if account_status is not None:
            conditions.append(Customer.account_status == account_status)
        active_subscription = Customer.subscriptions.any(
            Subscription.status == SubscriptionStatus.ACTIVE
        )
        if subscription == "active":
            conditions.append(active_subscription)
        elif subscription == "inactive":
            conditions.append(~active_subscription)
        normalized_search = (search or "").strip().casefold()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            conditions.append(
                or_(
                    func.lower(Customer.username).like(pattern),
                    func.lower(Customer.email).like(pattern),
                    func.lower(func.coalesce(Customer.phone_number, "")).like(pattern),
                )
            )

        customers = self.session.scalars(
            select(Customer)
            .options(
                joinedload(Customer.router),
                selectinload(Customer.subscriptions).joinedload(Subscription.package),
            )
            .where(*conditions)
            .order_by(Customer.created_at.desc())
            .limit(limit)
        ).all()
        matched_users = int(
            self.session.scalar(select(func.count(Customer.id)).where(*conditions)) or 0
        )
        total_users = int(self.session.scalar(select(func.count(Customer.id)).where(scope)) or 0)
        active_subscriptions = int(
            self.session.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.router_id.in_(router_ids),
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            )
            or 0
        )
        device_counts: dict[tuple[str, str], int] = {}
        for device_router_id, _session_id, username, _item in device_rows:
            key = (device_router_id, username.casefold())
            device_counts[key] = device_counts.get(key, 0) + 1

        customer_by_identity = {
            (customer.router_id, customer.username.casefold()): customer for customer in customers
        }
        search_pattern = normalized_search
        devices = []
        for device_router_id, session_id, username, item in device_rows:
            customer = customer_by_identity.get((device_router_id, username.casefold()))
            if (account_status is not None or subscription != "all") and customer is None:
                continue
            searchable = " ".join(
                [
                    username,
                    customer.email if customer else "",
                    customer.phone_number if customer and customer.phone_number else "",
                    str(item.get("address") or ""),
                    str(item.get("mac-address") or ""),
                ]
            ).casefold()
            if search_pattern and search_pattern not in searchable:
                continue
            devices.append(
                AdminConnectedDevice(
                    session_id=session_id,
                    username=username,
                    customer_email=customer.email if customer else None,
                    hostel_id=device_router_id,
                    hostel_name=router_names.get(device_router_id, device_router_id),
                    ip_address=_optional_text(item.get("address")),
                    mac_address=_optional_text(item.get("mac-address")),
                    uptime=_optional_text(item.get("uptime")),
                    login_method=_optional_text(item.get("login-by")),
                )
            )

        return AdminCustomerDirectoryResponse(
            generated_at=now,
            total_users=total_users,
            matched_users=matched_users,
            active_subscriptions=active_subscriptions,
            online_users=len(live_usernames),
            active_devices=len(device_rows),
            unavailable_routers=[
                live_status.name for live_status, _sessions in live_results if not live_status.reachable
            ],
            customers=[
                self._customer_detail(customer, live_usernames, device_counts)
                for customer in customers
            ],
            devices=devices,
        )

    @staticmethod
    def _customer_detail(
        customer: Customer,
        live_usernames: set[str],
        device_counts: dict[tuple[str, str], int],
    ) -> AdminCustomerDetail:
        current_subscription = next(
            (
                item
                for item in sorted(
                    customer.subscriptions,
                    key=lambda subscription: subscription.created_at,
                    reverse=True,
                )
                if item.status == SubscriptionStatus.ACTIVE
            ),
            None,
        )
        return AdminCustomerDetail(
            id=str(customer.id),
            username=customer.username,
            email=customer.email,
            phone_number=customer.phone_number,
            phone_verified=customer.phone_verified_at is not None,
            hostel_id=customer.router_id,
            hostel_name=customer.router.name,
            account_status=customer.account_status,
            subscription_status=(current_subscription.status if current_subscription else None),
            current_plan=(current_subscription.package.name if current_subscription else None),
            is_online=customer.username.casefold() in live_usernames,
            connected_devices=device_counts.get(
                (customer.router_id, customer.username.casefold()), 0
            ),
            joined_at=customer.created_at,
            last_login_at=customer.last_login_at,
            last_activity_at=customer.last_activity_at,
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

    def _live_router_sessions(
        self, router: Router
    ) -> tuple[DashboardRouterStatus, list[dict[str, str]]]:
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
                [],
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
                [],
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
            sessions,
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
