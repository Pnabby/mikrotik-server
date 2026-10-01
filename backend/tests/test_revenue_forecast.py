import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.customer import Customer
from app.models.enums import PaymentStatus
from app.models.package import Package
from app.models.router import Router
from app.models.transaction import Transaction
from app.services.admin_dashboard import AdminDashboardService
from app.services.revenue_forecast import forecast_revenue

TODAY = date(2026, 10, 1)


def _forecast(values):
    start = TODAY - timedelta(days=len(values))
    return forecast_revenue(
        currency="GHS", today=TODAY, first_sale_date=start,
        daily_revenue={start + timedelta(days=index): Decimal(str(value))
                       for index, value in enumerate(values)},
    )


def test_constant_revenue_forecast_and_totals():
    result = _forecast([100] * 28)
    assert result.available
    assert result.history_days == 28
    assert result.history_to == TODAY - timedelta(days=1)
    assert result.recent_daily_average == Decimal("100.00")
    assert result.weekly_change_percent == 0
    assert set(result.horizons) == {1, 7, 30}
    assert result.horizons[1].projected_revenue == Decimal("100.00")
    assert len(result.horizons[1].daily) == 1
    assert result.horizons[1].date_from == result.horizons[1].date_to == TODAY + timedelta(days=1)
    assert result.horizons[7].projected_revenue == Decimal("700.00")
    assert result.horizons[30].projected_revenue == Decimal("3000.00")
    for days, horizon in result.horizons.items():
        assert horizon.date_from == TODAY + timedelta(days=1)
        assert horizon.date_to == TODAY + timedelta(days=days)
        assert horizon.projected_revenue == sum(point.revenue for point in horizon.daily)
        assert horizon.lower_revenue <= horizon.projected_revenue <= horizon.upper_revenue
        assert all(Decimal(0) <= point.lower <= point.revenue <= point.upper
                   for point in horizon.daily)
    assert result.horizons[30].daily[-1].upper - result.horizons[30].daily[-1].lower > (
        result.horizons[7].daily[0].upper - result.horizons[7].daily[0].lower
    )


@pytest.mark.parametrize("days", [0, 1, 13])
def test_insufficient_history_is_unavailable(days):
    result = _forecast([100] * days)
    assert not result.available
    assert result.horizons == {}
    assert "14 completed days" in result.reason


def test_weekday_patterns_are_preserved():
    start = TODAY - timedelta(days=28)
    values = [200 if (start + timedelta(days=index)).weekday() >= 5 else 100
              for index in range(28)]
    result = _forecast(values)
    assert result.weekly_change_percent == 0
    assert result.horizons[7].projected_revenue == Decimal("900.00")
    for point in result.horizons[7].daily:
        assert point.revenue == (Decimal(200) if point.date.weekday() >= 5 else Decimal(100))


def test_growth_and_decline_follow_recent_trend_without_runaway_extrapolation():
    growing = _forecast([100] * 21 + [200] * 7)
    declining = _forecast([200] * 21 + [100] * 7)
    assert growing.weekly_change_percent == 100
    assert declining.weekly_change_percent == -50
    assert growing.horizons[7].projected_revenue > Decimal(1400)
    assert declining.horizons[7].projected_revenue < Decimal(700)
    assert max(point.revenue for point in growing.horizons[30].daily) < Decimal(275)
    assert min(point.revenue for point in declining.horizons[30].daily) >= Decimal(0)


def test_zero_sales_days_are_included_and_empty_history_is_unavailable():
    result = forecast_revenue(
        currency="GHS", today=TODAY, first_sale_date=TODAY - timedelta(days=28),
        daily_revenue={TODAY - timedelta(days=2): Decimal(700)},
    )
    assert result.available
    assert result.recent_daily_average == Decimal(100)
    assert len([point for point in result.history if point.revenue == 0]) == 27
    empty = _forecast([0] * 28)
    assert not empty.available
    assert "No paid revenue" in empty.reason


def test_forecast_query_scopes_hostels_currencies_status_and_completed_days():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def add_char_length(connection, _record):
        connection.create_function("char_length", 1, len)

    Base.metadata.create_all(engine)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(Router(id="hall", name="Hall", vpn_host="hall.example", api_port=8728))
        customer = Customer(
            id=uuid.uuid4(), router_id="hall", email="ama@example.com", username="ama",
            pin_hash="hash", mikrotik_user_verified_at=now, last_activity_at=now,
            terms_accepted_at=now, terms_version="1", privacy_notice_version="1",
        )
        package = Package(id=uuid.uuid4(), code="weekly", name="Weekly", amount=Decimal(100))
        session.add_all([customer, package])
        session.flush()

        def payment(day, amount, currency="GHS", status=PaymentStatus.SUCCESS, hostel="hall"):
            session.add(Transaction(
                customer_id=customer.id, package_id=package.id, router_id=hostel,
                paystack_reference=uuid.uuid4().hex, amount=Decimal(amount), currency=currency,
                payment_status=status, paid_at=day, created_at=day,
            ))

        for index in range(1, 29):
            payment(now - timedelta(days=index), "100")
            payment(now - timedelta(days=index), "10", currency="USD")
            payment(now - timedelta(days=index), "9000", status=PaymentStatus.PENDING)
            payment(now - timedelta(days=index), "9000", status=PaymentStatus.FAILED)
            payment(now - timedelta(days=index), "9000", hostel="other")
        payment(now, "999999")  # Today's incomplete total must not influence the forecast.
        payment(now - timedelta(days=80), "999999")  # Outside the baseline window.
        session.commit()
        results = AdminDashboardService(session)._revenue_forecasts(["hall"], TODAY)
        assert results["GHS"].history_days == 28
        assert results["GHS"].horizons[7].projected_revenue == Decimal(700)
        assert results["USD"].horizons[7].projected_revenue == Decimal(70)
        assert set(results) == {"GHS", "USD"}
        assert all(point.revenue == Decimal(100) for point in results["GHS"].history)
