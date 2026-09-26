from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from ipaddress import ip_network

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.registry import RouterDefinition
from app.models.activation import Activation
from app.models.customer import Customer
from app.models.enums import AccountStatus, PaymentStatus, SubscriptionStatus
from app.models.package import Package, RouterPackageProfile
from app.models.router import Router
from app.models.router_hourly_metric import RouterHourlyMetric
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.admin_dashboard import (
    AdminAccessPointListResponse,
    AdminAccessPointStatus,
    AdminAnalyticsResponse,
    AdminConnectedDevice,
    AdminCustomerDetail,
    AdminCustomerDirectoryResponse,
    AdminDashboardResponse,
    AdminHostelAnalytics,
    AdminHostelRevenue,
    AdminNetworkUsageResponse,
    AdminPlanRevenue,
    AdminRouterAnalytics,
    AdminTransactionDetail,
    AdminTransactionListResponse,
    AnalyticsDailyPoint,
    DashboardRevenue,
    DashboardRouterStatus,
    RouterHourlyProfilePoint,
    RouterPerformanceSummary,
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


def enabled_hotspot_usernames(users: list[dict[str, str]]) -> set[str]:
    """Return unique RouterOS HotSpot users that are not disabled."""
    disabled_values = {"1", "on", "true", "yes"}
    return {
        str(item.get("name", "")).strip().casefold()
        for item in users
        if str(item.get("name", "")).strip()
        and str(item.get("disabled", "no")).strip().casefold() not in disabled_values
    }


def _optional_text(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


class AdminDashboardService:
    """Build a database summary enriched with live, failure-isolated router data."""

    def __init__(self, session: Session):
        self.session = session

    def access_points(self, router: Router) -> AdminAccessPointListResponse:
        """Report the fixed AP address range (.2-.35) for one hostel."""
        network_text = router.hotspot_network or ""
        try:
            network = ip_network(network_text, strict=False)
            if network.version != 4:
                raise ValueError
        except ValueError:
            return self._access_point_response(
                router, network_text, [], False,
                "The hostel does not have a valid IPv4 network configured.",
            )

        # AP numbering is anchored to the first /24 represented by the configured
        # network (for example 192.168.88.2 through .35 for 192.168.88.0/23).
        addresses = [str(network.network_address + suffix) for suffix in range(2, 36)]
        try:
            with mikrotik_client_context(self._definition(router)) as client:
                leases = client.get_dhcp_leases()
                bridge_hosts = client.get_bridge_hosts()
        except (HTTPException, ValueError):
            return self._access_point_response(
                router, str(network), [], False, "Router could not be reached."
            )

        leases_by_address: dict[str, dict[str, str]] = {}
        for lease in leases:
            for key in ("active-address", "address"):
                address = _optional_text(lease.get(key))
                if address in addresses:
                    current = leases_by_address.get(address)
                    if current is None or (
                        not _optional_text(current.get("active-mac-address"))
                        and _optional_text(lease.get("active-mac-address"))
                    ):
                        leases_by_address[address] = lease

        ports_by_mac = {
            str(host.get("mac-address", "")).strip().casefold(): _optional_text(
                host.get("on-interface") or host.get("interface")
            )
            for host in bridge_hosts
            if _optional_text(host.get("mac-address"))
        }

        points = []
        for address in addresses:
            lease = leases_by_address.get(address)
            if lease is None:
                continue
            active_mac = _optional_text(lease.get("active-mac-address"))
            configured_mac = _optional_text(lease.get("mac-address"))
            points.append(AdminAccessPointStatus(
                ip_address=address,
                online=active_mac is not None,
                configured_mac=configured_mac,
                active_mac=active_mac,
                host_name=_optional_text(lease.get("host-name")),
                comment=_optional_text(lease.get("comment")),
                connected_port=ports_by_mac.get(
                    (active_mac or configured_mac or "").casefold()
                ),
                lease_status=_optional_text(lease.get("status")),
                last_seen=_optional_text(lease.get("last-seen")),
                expires_after=_optional_text(lease.get("expires-after")),
            ))
        online_count = sum(point.online for point in points)
        return AdminAccessPointListResponse(
            generated_at=datetime.now(UTC), router_id=router.id, hostel_name=router.name,
            network=str(network), router_reachable=True, online_count=online_count,
            offline_count=len(points) - online_count, access_points=points,
        )

    @staticmethod
    def _access_point_response(router, network, addresses, reachable, error):
        points = [AdminAccessPointStatus(ip_address=address, online=False) for address in addresses]
        return AdminAccessPointListResponse(
            generated_at=datetime.now(UTC), router_id=router.id, hostel_name=router.name,
            network=network, router_reachable=reachable, error=error, online_count=0,
            offline_count=len(points), access_points=points,
        )

    def network_usage(self, router: Router) -> AdminNetworkUsageResponse:
        """Read live and cumulative WAN traffic from the hostel's ether1 interface."""
        if not router.is_active:
            return self._network_usage_response(
                router,
                error="The hostel router is inactive.",
            )
        try:
            with mikrotik_client_context(self._definition(router)) as client:
                traffic = client.get_interface_traffic("ether1")
        except (HTTPException, ValueError):
            return self._network_usage_response(
                router,
                error="Router or ether1 traffic counters could not be reached.",
            )

        download_bytes = int(traffic["download_bytes"])
        upload_bytes = int(traffic["upload_bytes"])
        return AdminNetworkUsageResponse(
            generated_at=datetime.now(UTC),
            router_id=router.id,
            hostel_name=router.name,
            interface_name=str(traffic["name"]),
            router_reachable=True,
            interface_running=bool(traffic["running"]) and not bool(traffic["disabled"]),
            download_bps=int(traffic["download_bps"]),
            upload_bps=int(traffic["upload_bps"]),
            total_download_bytes=download_bytes,
            total_upload_bytes=upload_bytes,
            total_usage_bytes=download_bytes + upload_bytes,
        )

    @staticmethod
    def _network_usage_response(
        router: Router,
        *,
        error: str,
    ) -> AdminNetworkUsageResponse:
        return AdminNetworkUsageResponse(
            generated_at=datetime.now(UTC),
            router_id=router.id,
            hostel_name=router.name,
            interface_name="ether1",
            router_reachable=False,
            interface_running=False,
            error=error,
            download_bps=0,
            upload_bps=0,
            total_download_bytes=0,
            total_upload_bytes=0,
            total_usage_bytes=0,
        )

    def summary(self, router_id: str | None = None) -> AdminDashboardResponse:
        now = datetime.now(UTC)
        routers = self._routers(router_id)
        router_ids = [router.id for router in routers]
        customer_filter = Customer.router_id.in_(router_ids)
        user_counts_by_router = dict(
            self.session.execute(
                select(Customer.router_id, func.count(Customer.id))
                .where(customer_filter)
                .group_by(Customer.router_id)
            ).all()
        )

        live_statuses: list[DashboardRouterStatus] = []
        active_usernames: set[str] = set()
        active_device_keys: set[tuple[str, str, str]] = set()
        if routers:
            with ThreadPoolExecutor(max_workers=min(8, len(routers))) as executor:
                live_results = list(executor.map(self._live_router_status, routers))
        else:
            live_results = []
        for status, usernames, device_keys in live_results:
            status.total_users = user_counts_by_router.get(status.router_id, 0)
            live_statuses.append(status)
            active_usernames.update(usernames)
            active_device_keys.update(device_keys)

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
        active_subscriptions = sum(status.active_subscriptions for status in live_statuses)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today_start.replace(day=1)
        seven_day_start = today_start.date() - timedelta(days=6)

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
            revenue_last_7_days=self._daily_analytics(
                router_ids,
                seven_day_start,
                today_start.date(),
            ),
            routers=live_statuses,
        )

    def analytics(
        self,
        *,
        router_id: str | None,
        days: int,
        date_from: date | None = None,
        date_to: date | None = None,
        all_time: bool = False,
    ) -> AdminAnalyticsResponse:
        now = datetime.now(UTC)
        routers = self._routers(router_id, include_inactive=True)
        router_ids = [router.id for router in routers]
        occurred_at = func.coalesce(Transaction.paid_at, Transaction.created_at)

        if all_time and (date_from is not None or date_to is not None):
            raise HTTPException(status_code=400, detail="Choose all time or a custom period.")
        if (date_from is None) != (date_to is None):
            raise HTTPException(status_code=400, detail="Both custom dates are required.")
        if date_from is not None and date_to is not None and date_to < date_from:
            raise HTTPException(status_code=400, detail="End date cannot be before start date.")

        comparison_available = not all_time
        if all_time:
            earliest_transaction = self.session.scalar(
                select(func.min(occurred_at)).where(Transaction.router_id.in_(router_ids))
            )
            earliest_customer = self.session.scalar(
                select(func.min(Customer.created_at)).where(Customer.router_id.in_(router_ids))
            )
            earliest_metric = self.session.scalar(
                select(func.min(RouterHourlyMetric.hour)).where(
                    RouterHourlyMetric.router_id.in_(router_ids)
                )
            )
            earliest_dates = [
                date.fromisoformat(str(value)[:10])
                for value in (earliest_transaction, earliest_customer, earliest_metric)
                if value is not None
            ]
            date_to = now.date()
            date_from = min(earliest_dates, default=date_to)
        elif date_from is None or date_to is None:
            date_to = now.date()
            date_from = date_to - timedelta(days=days - 1)

        period_days = (date_to - date_from).days + 1
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=period_days - 1)
        current_start = datetime.combine(date_from, time.min, tzinfo=UTC)
        current_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        previous_start = datetime.combine(previous_from, time.min, tzinfo=UTC)
        previous_end = datetime.combine(previous_to + timedelta(days=1), time.min, tzinfo=UTC)
        scope = Transaction.router_id.in_(router_ids)
        current_conditions = [scope, occurred_at >= current_start, occurred_at < current_end]
        previous_conditions = [
            scope,
            occurred_at >= previous_start,
            occurred_at < previous_end,
        ]
        successful = Transaction.payment_status == PaymentStatus.SUCCESS

        def revenue_for(conditions: list) -> dict[str, Decimal]:
            return {
                currency: amount or Decimal(0)
                for currency, amount in self.session.execute(
                    select(Transaction.currency, func.sum(Transaction.amount))
                    .where(*conditions, successful)
                    .group_by(Transaction.currency)
                )
            }

        def successful_count(conditions: list) -> int:
            return int(
                self.session.scalar(
                    select(func.count(Transaction.id)).where(*conditions, successful)
                )
                or 0
            )

        revenue = revenue_for(current_conditions)
        previous_revenue = revenue_for(previous_conditions) if comparison_available else {}
        successful_sales = successful_count(current_conditions)
        previous_successful_sales = (
            successful_count(previous_conditions) if comparison_available else 0
        )
        status_counts = {
            payment_status: int(count)
            for payment_status, count in self.session.execute(
                select(Transaction.payment_status, func.count(Transaction.id))
                .where(*current_conditions)
                .group_by(Transaction.payment_status)
            )
        }
        payment_attempts = sum(status_counts.values())
        average_order_value = {
            currency: Decimal(str(average or 0)).quantize(Decimal("0.01"))
            for currency, average in self.session.execute(
                select(Transaction.currency, func.avg(Transaction.amount))
                .where(*current_conditions, successful)
                .group_by(Transaction.currency)
            )
        }

        customer_scope = Customer.router_id.in_(router_ids)
        new_customers = int(
            self.session.scalar(
                select(func.count(Customer.id)).where(
                    customer_scope,
                    Customer.created_at >= current_start,
                    Customer.created_at < current_end,
                )
            )
            or 0
        )
        previous_new_customers = (
            int(
                self.session.scalar(
                    select(func.count(Customer.id)).where(
                        customer_scope,
                        Customer.created_at >= previous_start,
                        Customer.created_at < previous_end,
                    )
                )
                or 0
            )
            if comparison_available
            else 0
        )
        total_customers = int(
            self.session.scalar(select(func.count(Customer.id)).where(customer_scope)) or 0
        )
        user_counts = {
            hostel_id: int(count)
            for hostel_id, count in self.session.execute(
                select(Customer.router_id, func.count(Customer.id))
                .where(customer_scope)
                .group_by(Customer.router_id)
            )
        }
        hostel_performance = [
            AdminHostelAnalytics(
                hostel_id=hostel.hostel_id,
                hostel_name=hostel.hostel_name,
                revenue=hostel.revenue,
                successful_sales=hostel.successful_sales,
                total_users=user_counts.get(hostel.hostel_id, 0),
            )
            for hostel in self._hostel_revenue(routers, current_conditions)
        ]
        primary_currency = max(revenue, key=lambda currency: revenue[currency], default="GHS")

        return AdminAnalyticsResponse(
            generated_at=now,
            router_id=router_id,
            period_days=period_days,
            comparison_available=comparison_available,
            date_from=date_from,
            date_to=date_to,
            primary_currency=primary_currency,
            revenue=revenue,
            previous_revenue=previous_revenue,
            average_order_value=average_order_value,
            successful_sales=successful_sales,
            previous_successful_sales=previous_successful_sales,
            pending_payments=status_counts.get(PaymentStatus.PENDING, 0),
            failed_payments=status_counts.get(PaymentStatus.FAILED, 0),
            success_rate=round(successful_sales / payment_attempts * 100, 1)
            if payment_attempts
            else 0,
            new_customers=new_customers,
            previous_new_customers=previous_new_customers,
            total_customers=total_customers,
            daily=self._daily_analytics(router_ids, date_from, date_to),
            plan_performance=self._plan_revenue(router_ids, current_conditions, search=""),
            hostel_performance=hostel_performance,
            router_analytics=self._router_analytics(
                routers, current_start=current_start, current_end=current_end
            ),
        )

    def _router_analytics(
        self,
        routers: list[Router],
        *,
        current_start: datetime,
        current_end: datetime,
    ) -> AdminRouterAnalytics:
        router_ids = [router.id for router in routers]
        rows = list(
            self.session.scalars(
                select(RouterHourlyMetric)
                .where(
                    RouterHourlyMetric.router_id.in_(router_ids),
                    RouterHourlyMetric.hour >= current_start,
                    RouterHourlyMetric.hour < current_end,
                )
                .order_by(RouterHourlyMetric.hour)
            )
        )
        if not rows:
            return AdminRouterAnalytics(
                available=False,
                baseline_days=0,
                prediction_ready=False,
                days_until_prediction=7,
                predicted_peak_hours=[],
                hourly_profile=[],
                routers=[],
            )

        def summarize(
            metric_rows: list[RouterHourlyMetric],
            *,
            name: str,
            router_id: str | None,
        ) -> RouterPerformanceSummary:
            successful = sum(max(row.sample_count - row.failed_samples, 0) for row in metric_rows)
            attempts = sum(row.sample_count for row in metric_rows)

            def weighted(attribute: str) -> float:
                if not successful:
                    return 0.0
                return sum(
                    float(getattr(row, attribute))
                    * max(row.sample_count - row.failed_samples, 0)
                    for row in metric_rows
                ) / successful

            sensor_rows = [
                row for row in metric_rows if row.temperature_avg is not None
            ]
            voltage_rows = [row for row in metric_rows if row.voltage_avg is not None]
            running_samples = sum(row.interface_running_samples for row in metric_rows)
            latest_row = max(metric_rows, key=lambda row: row.last_sample_at)
            return RouterPerformanceSummary(
                router_id=router_id,
                router_name=name,
                successful_samples=successful,
                failed_samples=sum(row.failed_samples for row in metric_rows),
                average_devices=round(weighted("active_devices_avg"), 1),
                peak_devices=max((row.active_devices_peak for row in metric_rows), default=0),
                average_cpu_percent=round(weighted("cpu_usage_avg"), 1),
                peak_cpu_percent=round(max((row.cpu_usage_peak for row in metric_rows), default=0), 1),
                average_memory_percent=round(weighted("memory_usage_avg"), 1),
                peak_memory_percent=round(max((row.memory_usage_peak for row in metric_rows), default=0), 1),
                average_free_memory_bytes=round(weighted("memory_free_bytes_avg"), 1),
                average_download_bps=round(weighted("download_bps_avg"), 1),
                peak_download_bps=max((row.download_bps_peak for row in metric_rows), default=0),
                average_upload_bps=round(weighted("upload_bps_avg"), 1),
                peak_upload_bps=max((row.upload_bps_peak for row in metric_rows), default=0),
                downloaded_bytes=sum(row.download_bytes for row in metric_rows),
                uploaded_bytes=sum(row.upload_bytes for row in metric_rows),
                interface_availability_percent=round(running_samples / successful * 100, 1)
                if successful
                else 0,
                collection_success_percent=round(successful / attempts * 100, 1)
                if attempts
                else 0,
                current_uptime_seconds=latest_row.uptime_seconds,
                restart_count=sum((row.restart_count or 0) for row in metric_rows),
                average_temperature=round(
                    sum(float(row.temperature_avg) for row in sensor_rows) / len(sensor_rows), 1
                ) if sensor_rows else None,
                average_voltage=round(
                    sum(float(row.voltage_avg) for row in voltage_rows) / len(voltage_rows), 1
                ) if voltage_rows else None,
            )

        rows_by_router = {
            router.id: [row for row in rows if row.router_id == router.id] for router in routers
        }
        router_summaries = [
            summarize(rows_by_router[router.id], name=router.name, router_id=router.id)
            for router in routers
            if rows_by_router[router.id]
        ]
        hour_rows = {
            hour: [row for row in rows if row.hour.hour == hour] for hour in range(24)
        }
        hour_device_averages: dict[int, float] = {}
        for hour, grouped_rows in hour_rows.items():
            successful = sum(max(row.sample_count - row.failed_samples, 0) for row in grouped_rows)
            hour_device_averages[hour] = (
                sum(
                    row.active_devices_avg * max(row.sample_count - row.failed_samples, 0)
                    for row in grouped_rows
                ) / successful
                if successful
                else 0
            )
        populated_hours = [hour for hour, grouped_rows in hour_rows.items() if grouped_rows]
        peak_hours = sorted(
            populated_hours,
            key=lambda hour: (hour_device_averages[hour], hour),
            reverse=True,
        )[:3]
        peak_hour_set = set(peak_hours)
        profile = []
        for hour in range(24):
            grouped_rows = hour_rows[hour]
            successful = sum(max(row.sample_count - row.failed_samples, 0) for row in grouped_rows)

            def hour_weighted(
                attribute: str,
                metric_rows: list[RouterHourlyMetric] = grouped_rows,
                sample_count: int = successful,
            ) -> float:
                return (
                    sum(
                        float(getattr(row, attribute))
                        * max(row.sample_count - row.failed_samples, 0)
                        for row in metric_rows
                    ) / sample_count
                    if sample_count
                    else 0
                )

            profile.append(
                RouterHourlyProfilePoint(
                    hour=hour,
                    label=datetime(2000, 1, 1, hour, tzinfo=UTC).strftime("%I %p").lstrip("0"),
                    samples=successful,
                    average_devices=round(hour_weighted("active_devices_avg"), 1),
                    peak_devices=max((row.active_devices_peak for row in grouped_rows), default=0),
                    average_cpu_percent=round(hour_weighted("cpu_usage_avg"), 1),
                    average_memory_percent=round(hour_weighted("memory_usage_avg"), 1),
                    average_download_bps=round(hour_weighted("download_bps_avg"), 1),
                    average_upload_bps=round(hour_weighted("upload_bps_avg"), 1),
                    predicted_peak=hour in peak_hour_set,
                )
            )
        baseline_days = len({row.hour.date() for row in rows})
        return AdminRouterAnalytics(
            available=True,
            collection_started_at=min(row.hour for row in rows),
            last_collected_at=max(row.last_sample_at for row in rows),
            baseline_days=baseline_days,
            prediction_ready=baseline_days >= 7,
            days_until_prediction=max(7 - baseline_days, 0),
            predicted_peak_hours=sorted(peak_hours),
            summary=summarize(rows, name="All selected hostels", router_id=None),
            hourly_profile=profile,
            routers=router_summaries,
        )

    def _daily_analytics(
        self,
        router_ids: list[str],
        date_from: date,
        date_to: date,
    ) -> list[AnalyticsDailyPoint]:
        occurred_at = func.coalesce(Transaction.paid_at, Transaction.created_at)
        date_bucket = func.date(occurred_at)
        start = datetime.combine(date_from, time.min, tzinfo=UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        points = {
            date_from + timedelta(days=index): {
                "revenue": {},
                "successful_sales": 0,
                "new_customers": 0,
            }
            for index in range((date_to - date_from).days + 1)
        }

        for day_value, currency, sales, revenue in self.session.execute(
            select(
                date_bucket,
                Transaction.currency,
                func.count(Transaction.id),
                func.sum(Transaction.amount),
            )
            .where(
                Transaction.router_id.in_(router_ids),
                Transaction.payment_status == PaymentStatus.SUCCESS,
                occurred_at >= start,
                occurred_at < end,
            )
            .group_by(date_bucket, Transaction.currency)
        ):
            day = day_value if isinstance(day_value, date) else date.fromisoformat(str(day_value))
            if day not in points:
                continue
            points[day]["revenue"][currency] = revenue or Decimal(0)
            points[day]["successful_sales"] += int(sales)

        customer_date_bucket = func.date(Customer.created_at)
        for day_value, customers in self.session.execute(
            select(customer_date_bucket, func.count(Customer.id))
            .where(
                Customer.router_id.in_(router_ids),
                Customer.created_at >= start,
                Customer.created_at < end,
            )
            .group_by(customer_date_bucket)
        ):
            day = day_value if isinstance(day_value, date) else date.fromisoformat(str(day_value))
            if day in points:
                points[day]["new_customers"] = int(customers)

        return [
            AnalyticsDailyPoint(date=day, **values)
            for day, values in points.items()
        ]

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

        routers = self._routers(router_id, include_inactive=True)
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
            profile_search_mapping = aliased(RouterPackageProfile)
            matching_profile = (
                select(profile_search_mapping.id)
                .where(
                    profile_search_mapping.router_id == Transaction.router_id,
                    profile_search_mapping.package_id == Transaction.package_id,
                    or_(
                        func.lower(profile_search_mapping.mikrotik_profile).like(pattern),
                        func.lower(func.coalesce(profile_search_mapping.display_name, "")).like(
                            pattern
                        ),
                    ),
                )
                .exists()
            )
            conditions.append(
                or_(
                    func.lower(Transaction.paystack_reference).like(pattern),
                    func.lower(Customer.username).like(pattern),
                    func.lower(Customer.email).like(pattern),
                    func.lower(Package.name).like(pattern),
                    matching_profile,
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
        transactions = self.session.scalars(
            base_query.order_by(occurred_at.desc()).offset(offset).limit(limit)
        ).all()

        return AdminTransactionListResponse(
            generated_at=datetime.now(UTC),
            total=total,
            offset=offset,
            limit=limit,
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

    def _plan_revenue(
        self,
        router_ids: list[str],
        conditions: list,
        *,
        search: str,
    ) -> list[AdminPlanRevenue]:
        successful = Transaction.payment_status == PaymentStatus.SUCCESS
        profile_name = func.coalesce(
            RouterPackageProfile.mikrotik_profile,
            Activation.target_profile,
            Package.code,
        )
        normalized_profile = func.lower(profile_name)
        rows = self.session.execute(
            select(
                normalized_profile,
                func.max(profile_name),
                func.max(func.coalesce(RouterPackageProfile.display_name, Package.name)),
                Transaction.currency,
                func.count(Transaction.id).filter(successful),
                func.coalesce(func.sum(Transaction.amount).filter(successful), 0),
                func.count(func.distinct(Transaction.router_id)).filter(successful),
            )
            .join(Customer, Transaction.customer_id == Customer.id)
            .join(Package, Transaction.package_id == Package.id)
            .outerjoin(Activation, Activation.transaction_id == Transaction.id)
            .outerjoin(
                RouterPackageProfile,
                and_(
                    RouterPackageProfile.router_id == Transaction.router_id,
                    RouterPackageProfile.package_id == Transaction.package_id,
                ),
            )
            .where(*conditions)
            .group_by(
                normalized_profile,
                Transaction.currency,
            )
        ).all()

        mappings = self.session.scalars(
            select(RouterPackageProfile)
            .options(joinedload(RouterPackageProfile.package), joinedload(RouterPackageProfile.router))
            .where(RouterPackageProfile.router_id.in_(router_ids))
        ).all()
        metadata: dict[tuple[str, str], dict[str, object]] = {}
        for mapping in mappings:
            key = (mapping.mikrotik_profile.casefold(), mapping.package.currency)
            entry = metadata.setdefault(
                key,
                {
                    "profile": mapping.mikrotik_profile,
                    "display_names": set(),
                    "hostel_ids": set(),
                    "search_match": False,
                },
            )
            entry["display_names"].add(mapping.display_name or mapping.package.name)
            entry["hostel_ids"].add(mapping.router_id)
            searchable = " ".join(
                [
                    mapping.mikrotik_profile,
                    mapping.display_name or "",
                    mapping.package.name,
                    mapping.package.code,
                ]
            ).casefold()
            entry["search_match"] = bool(entry["search_match"] or search in searchable)

        plan_rows: dict[tuple[str, str], dict[str, object]] = {}
        for row in rows:
            (
                normalized_name,
                observed_profile,
                observed_display_name,
                currency,
                successful_sales,
                revenue,
                selling_hostel_count,
            ) = row
            key = (str(normalized_name), currency)
            mapping_metadata = metadata.get(key)
            display_names = mapping_metadata["display_names"] if mapping_metadata else set()
            plan_rows[key] = {
                "profile": (
                    mapping_metadata["profile"] if mapping_metadata else str(observed_profile)
                ),
                "display_name": (
                    next(iter(display_names))
                    if len(display_names) == 1
                    else str(observed_display_name or observed_profile)
                ),
                "currency": currency,
                "successful_revenue": revenue or Decimal(0),
                "successful_sales": int(successful_sales),
                "hostel_count": (
                    len(mapping_metadata["hostel_ids"])
                    if mapping_metadata
                    else int(selling_hostel_count)
                ),
            }

        for key, mapping_metadata in metadata.items():
            if key in plan_rows:
                continue
            if search and not mapping_metadata["search_match"]:
                continue
            display_names = mapping_metadata["display_names"]
            plan_rows[key] = {
                "profile": mapping_metadata["profile"],
                "display_name": (
                    next(iter(display_names))
                    if len(display_names) == 1
                    else mapping_metadata["profile"]
                ),
                "currency": key[1],
                "successful_revenue": Decimal(0),
                "successful_sales": 0,
                "hostel_count": len(mapping_metadata["hostel_ids"]),
            }

        totals_by_currency: dict[str, Decimal] = {}
        for item in plan_rows.values():
            totals_by_currency[item["currency"]] = (
                totals_by_currency.get(item["currency"], Decimal(0))
                + item["successful_revenue"]
            )
        result = [
            AdminPlanRevenue(
                **item,
                revenue_share_percent=round(
                    float(
                        item["successful_revenue"]
                        / totals_by_currency[item["currency"]]
                        * 100
                    ),
                    1,
                )
                if totals_by_currency[item["currency"]]
                else 0,
            )
            for item in plan_rows.values()
        ]
        return sorted(
            result,
            key=lambda item: (
                -item.successful_revenue,
                -item.successful_sales,
                item.display_name.casefold(),
            ),
        )

    def _hostel_revenue(
        self,
        routers: list[Router],
        conditions: list,
    ) -> list[AdminHostelRevenue]:
        successful = Transaction.payment_status == PaymentStatus.SUCCESS
        rows = self.session.execute(
            select(
                Transaction.router_id,
                Transaction.currency,
                func.count(Transaction.id),
                func.coalesce(func.sum(Transaction.amount), 0),
            )
            .join(Customer, Transaction.customer_id == Customer.id)
            .join(Package, Transaction.package_id == Package.id)
            .where(*conditions, successful)
            .group_by(Transaction.router_id, Transaction.currency)
        ).all()
        by_hostel: dict[str, dict[str, object]] = {
            router.id: {"revenue": {}, "successful_sales": 0} for router in routers
        }
        for hostel_id, currency, successful_sales, revenue in rows:
            entry = by_hostel[hostel_id]
            entry["revenue"][currency] = revenue or Decimal(0)
            entry["successful_sales"] += int(successful_sales)
        return [
            AdminHostelRevenue(
                hostel_id=router.id,
                hostel_name=router.name,
                revenue=by_hostel[router.id]["revenue"],
                successful_sales=by_hostel[router.id]["successful_sales"],
            )
            for router in routers
        ]

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
        active_subscriptions = sum(
            live_status.active_subscriptions for live_status, _sessions in live_results
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

    def _routers(
        self, router_id: str | None, *, include_inactive: bool = False
    ) -> list[Router]:
        query = select(Router).order_by(Router.display_order, Router.name, Router.id)
        if router_id is not None:
            query = query.where(Router.id == router_id)
        elif not include_inactive:
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
                    active_subscriptions=0,
                    error="Hostel is inactive or not fully configured.",
                ),
                set(),
                set(),
            )

        try:
            with mikrotik_client_context(self._definition(router)) as client:
                sessions = client.get_hotspot_active_sessions()
                hotspot_users = client.get_hotspot_users()
        except HTTPException:
            return (
                DashboardRouterStatus(
                    router_id=router.id,
                    name=router.name,
                    reachable=False,
                    active_users=0,
                    active_devices=0,
                    active_subscriptions=0,
                    error="Router could not be reached.",
                ),
                set(),
                set(),
            )

        usernames, device_keys = active_identity_sets(router.id, sessions)
        enabled_usernames = enabled_hotspot_usernames(hotspot_users)
        return (
            DashboardRouterStatus(
                router_id=router.id,
                name=router.name,
                reachable=True,
                active_users=len(usernames),
                active_devices=len(device_keys),
                active_subscriptions=len(enabled_usernames),
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
                    active_subscriptions=0,
                    error="Hostel is inactive or not fully configured.",
                ),
                [],
            )
        try:
            with mikrotik_client_context(self._definition(router)) as client:
                sessions = client.get_hotspot_active_sessions()
                hotspot_users = client.get_hotspot_users()
        except HTTPException:
            return (
                DashboardRouterStatus(
                    router_id=router.id,
                    name=router.name,
                    reachable=False,
                    active_users=0,
                    active_devices=0,
                    active_subscriptions=0,
                    error="Router could not be reached.",
                ),
                [],
            )
        usernames, device_keys = active_identity_sets(router.id, sessions)
        enabled_usernames = enabled_hotspot_usernames(hotspot_users)
        return (
            DashboardRouterStatus(
                router_id=router.id,
                name=router.name,
                reachable=True,
                active_users=len(usernames),
                active_devices=len(device_keys),
                active_subscriptions=len(enabled_usernames),
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
