import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - registers every related table with metadata.
from app.db.base import Base
from app.models.customer import Customer
from app.models.enums import PaymentStatus
from app.models.package import Package, RouterPackageProfile
from app.models.router import Router
from app.models.transaction import Transaction
from app.services.admin_dashboard import AdminDashboardService


def test_transactions_and_analytics_keep_reporting_concerns_separate() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def add_char_length(connection, _record) -> None:
        connection.create_function("char_length", 1, len)

    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        router = Router(
            id="hall",
            name="Main Hall",
            vpn_host="hall.example",
            api_port=8728,
            hotspot_network="10.0.0.0/24",
        )
        annex = Router(
            id="annex",
            name="Annex",
            vpn_host="annex.example",
            api_port=8728,
            hotspot_network="10.1.0.0/24",
            is_active=False,
        )
        customer = Customer(
            id=uuid.uuid4(),
            router_id=router.id,
            email="ama@example.com",
            username="ama",
            pin_hash="hash",
            mikrotik_user_verified_at=now,
            last_activity_at=now,
            terms_accepted_at=now,
            terms_version="1",
            privacy_notice_version="1",
        )
        annex_customer = Customer(
            id=uuid.uuid4(),
            router_id=annex.id,
            email="kojo@example.com",
            username="kojo",
            pin_hash="hash",
            mikrotik_user_verified_at=now,
            last_activity_at=now,
            terms_accepted_at=now,
            terms_version="1",
            privacy_notice_version="1",
        )
        weekly = Package(
            id=uuid.uuid4(),
            code="hall-weekly",
            name="Weekly",
            amount=Decimal("10.00"),
            currency="GHS",
        )
        monthly = Package(
            id=uuid.uuid4(),
            code="hall-monthly",
            name="Monthly",
            amount=Decimal("30.00"),
            currency="GHS",
        )
        annex_weekly = Package(
            id=uuid.uuid4(),
            code="annex-weekly",
            name="Weekly",
            amount=Decimal("20.00"),
            currency="GHS",
        )
        session.add_all(
            [
                router,
                annex,
                customer,
                annex_customer,
                weekly,
                monthly,
                annex_weekly,
                RouterPackageProfile(
                    router_id=router.id,
                    package_id=weekly.id,
                    mikrotik_profile="weekly",
                    display_name="Weekly Plus",
                ),
                RouterPackageProfile(
                    router_id=router.id,
                    package_id=monthly.id,
                    mikrotik_profile="monthly",
                    display_name="Monthly Max",
                ),
                RouterPackageProfile(
                    router_id=annex.id,
                    package_id=annex_weekly.id,
                    mikrotik_profile="weekly",
                    display_name="Weekly Plus",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Transaction(
                    customer_id=customer.id,
                    package_id=weekly.id,
                    router_id=router.id,
                    paystack_reference="success-ref",
                    amount=Decimal("10.00"),
                    currency="GHS",
                    payment_status=PaymentStatus.SUCCESS,
                ),
                Transaction(
                    customer_id=customer.id,
                    package_id=weekly.id,
                    router_id=router.id,
                    paystack_reference="failed-ref",
                    amount=Decimal("10.00"),
                    currency="GHS",
                    payment_status=PaymentStatus.FAILED,
                ),
                Transaction(
                    customer_id=annex_customer.id,
                    package_id=annex_weekly.id,
                    router_id=annex.id,
                    paystack_reference="annex-success-ref",
                    amount=Decimal("20.00"),
                    currency="GHS",
                    payment_status=PaymentStatus.SUCCESS,
                ),
            ]
        )
        session.commit()

        result = AdminDashboardService(session).transactions(
            router_id=None,
            payment_status=None,
            date_from=None,
            date_to=None,
            search=None,
            offset=0,
            limit=100,
        )
        search_result = AdminDashboardService(session).transactions(
            router_id=None,
            payment_status=None,
            date_from=None,
            date_to=None,
            search="monthly",
            offset=0,
            limit=100,
        )
        service = AdminDashboardService(session)
        analytics = service.analytics(router_id=None, days=30)
        custom_analytics = service.analytics(
            router_id=None,
            days=30,
            date_from=now.date(),
            date_to=now.date(),
        )
        all_time_analytics = service.analytics(router_id=None, days=30, all_time=True)

    weekly_result = next(
        plan for plan in analytics.plan_performance if plan.profile == "weekly"
    )
    monthly_result = next(
        plan for plan in analytics.plan_performance if plan.profile == "monthly"
    )
    assert weekly_result.display_name == "Weekly Plus"
    assert weekly_result.successful_revenue == Decimal("30.00")
    assert weekly_result.successful_sales == 2
    assert weekly_result.hostel_count == 2
    assert weekly_result.revenue_share_percent == 100.0
    assert monthly_result.successful_sales == 0
    assert monthly_result.successful_revenue == Decimal(0)
    assert result.total == 3
    assert search_result.total == 0
    assert not hasattr(result, "revenue")
    hostel_revenue = {hostel.hostel_id: hostel for hostel in analytics.hostel_performance}
    assert hostel_revenue["hall"].revenue == {"GHS": Decimal("10.00")}
    assert hostel_revenue["annex"].revenue == {"GHS": Decimal("20.00")}
    assert analytics.revenue == {"GHS": Decimal("30.00")}
    assert analytics.successful_sales == 2
    assert analytics.failed_payments == 1
    assert analytics.success_rate == 66.7
    assert analytics.new_customers == 2
    assert sum(point.successful_sales for point in analytics.daily) == 2
    assert {hostel.hostel_id for hostel in analytics.hostel_performance} == {"hall", "annex"}
    assert custom_analytics.period_days == 1
    assert custom_analytics.comparison_available is True
    assert all_time_analytics.comparison_available is False
    assert all_time_analytics.previous_revenue == {}
    assert all_time_analytics.date_to == now.date()
