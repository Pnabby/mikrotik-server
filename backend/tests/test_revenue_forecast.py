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
    assert set(result.periods) == {
        "today", "tomorrow", "this_week", "next_week", "this_month", "next_month",
    }
    assert result.periods["today"].projected_revenue == Decimal("100.00")
    assert result.periods["tomorrow"].date_from == TODAY + timedelta(days=1)
    assert result.periods["this_week"].projected_revenue == Decimal("700.00")
    assert result.periods["next_week"].projected_revenue == Decimal("700.00")
    assert result.periods["this_month"].projected_revenue == Decimal("3100.00")
    assert result.periods["next_month"].projected_revenue == Decimal("3000.00")
    for period in result.periods.values():
        assert period.days == len(period.daily) == (period.date_to - period.date_from).days + 1
        assert period.projected_revenue == sum(point.revenue for point in period.daily)
        assert period.lower_revenue <= period.projected_revenue <= period.upper_revenue
        assert all(Decimal(0) <= point.lower <= point.revenue <= point.upper
                   for point in period.daily)
    assert result.periods["next_month"].daily[-1].upper - result.periods["next_month"].daily[-1].lower > (
        result.periods["tomorrow"].daily[0].upper - result.periods["tomorrow"].daily[0].lower
    )


@pytest.mark.parametrize("days", [0, 1, 13])
def test_insufficient_history_is_unavailable(days):
    result = _forecast([100] * days)
    assert not result.available
    assert result.periods == {}
    assert "14 completed days" in result.reason


def test_weekday_patterns_are_preserved():
    start = TODAY - timedelta(days=28)
    values = [200 if (start + timedelta(days=index)).weekday() >= 5 else 100
              for index in range(28)]
    result = _forecast(values)
    assert result.weekly_change_percent == 0
    assert result.periods["next_week"].projected_revenue == Decimal("900.00")
    for point in result.periods["next_week"].daily:
        assert point.revenue == (Decimal(200) if point.date.weekday() >= 5 else Decimal(100))


def test_growth_and_decline_follow_recent_trend_without_runaway_extrapolation():
    growing = _forecast([100] * 21 + [200] * 7)
    declining = _forecast([200] * 21 + [100] * 7)
    assert growing.weekly_change_percent == 100
    assert declining.weekly_change_percent == -50
    assert growing.periods["next_week"].projected_revenue > Decimal(1400)
    assert declining.periods["next_week"].projected_revenue < Decimal(700)
    assert max(point.revenue for point in growing.periods["next_month"].daily) < Decimal(275)
    assert min(point.revenue for point in declining.periods["next_month"].daily) >= Decimal(0)


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
        payment(now, "999999")  # Included in actuals, but excluded from model fitting.
        payment(now - timedelta(days=80), "999999")  # Outside the baseline window.
        session.commit()
        results = AdminDashboardService(session)._revenue_forecasts(["hall"], now)
        assert results["GHS"].history_days == 28
        assert results["GHS"].periods["next_week"].projected_revenue == Decimal(700)
        assert results["USD"].periods["next_week"].projected_revenue == Decimal(70)
        assert set(results) == {"GHS", "USD"}
        assert all(point.revenue == Decimal(100) for point in results["GHS"].history)

        assert results["GHS"].periods["today"].actual_revenue == Decimal(999999)
        assert results["GHS"].periods["today"].projected_revenue >= Decimal(999999)
        assert results["GHS"].periods["tomorrow"].actual_revenue is None

        # Late-month actuals must also include the first days outside the 28-day baseline.
        for index in range(31):
            payment(datetime(2026, 10, 1, 12, tzinfo=UTC) + timedelta(days=index), "10", currency="EUR")
        payment(datetime(2026, 10, 31, 20, tzinfo=UTC), "9999", currency="EUR")  # After snapshot.
        session.commit()
        october = AdminDashboardService(session)._revenue_forecasts(
            ["hall"], datetime(2026, 10, 31, 12, tzinfo=UTC))
        assert october["EUR"].periods["this_month"].actual_revenue == Decimal(310)
        assert october["EUR"].periods["next_month"].date_from == date(2026, 11, 1)


def test_current_period_combines_earned_revenue_with_remaining_predictions():
    today = date(2026, 10, 15)
    start = today - timedelta(days=28)
    revenue = {start + timedelta(days=index): Decimal(100) for index in range(28)}
    revenue[today] = Decimal(250)
    result = forecast_revenue(currency="GHS", today=today, first_sale_date=start,
                              daily_revenue=revenue)
    assert result.recent_daily_average == Decimal(100)
    assert result.periods["today"].actual_revenue == Decimal(250)
    assert result.periods["today"].projected_revenue == Decimal(250)
    assert result.periods["tomorrow"].projected_revenue == Decimal(100)
    current_month = result.periods["this_month"]
    assert current_month.actual_revenue == Decimal(1650)  # 14 completed days + today.
    assert current_month.projected_revenue == Decimal(3250)  # Plus 16 future days.
    assert current_month.lower_revenue >= current_month.actual_revenue
    assert all(not point.is_prediction for point in current_month.daily if point.date < today)
    assert all(point.actual_revenue is None for point in current_month.daily if point.date > today)


@pytest.mark.parametrize("today,current_days,next_start,next_days", [
    (date(2026, 12, 31), 31, date(2027, 1, 1), 31),
    (date(2028, 2, 15), 29, date(2028, 3, 1), 31),
    (date(2026, 2, 15), 28, date(2026, 3, 1), 31),
])
def test_month_forecasts_use_calendar_months_and_year_rollover(today, current_days, next_start, next_days):
    start = today - timedelta(days=28)
    result = forecast_revenue(currency="GHS", today=today, first_sale_date=start,
                              daily_revenue={start + timedelta(days=i): Decimal(10) for i in range(28)})
    assert result.periods["this_month"].date_from == today.replace(day=1)
    assert result.periods["this_month"].days == current_days
    assert result.periods["next_month"].date_from == next_start
    assert result.periods["next_month"].days == next_days
    assert result.periods["next_month"].actual_revenue is None


def test_week_forecast_runs_monday_to_sunday_across_month_boundary():
    today = date(2026, 11, 1)  # Sunday.
    start = today - timedelta(days=28)
    result = forecast_revenue(currency="GHS", today=today, first_sale_date=start,
                              daily_revenue={start + timedelta(days=i): Decimal(10) for i in range(28)})
    assert result.periods["this_week"].date_from == date(2026, 10, 26)
    assert result.periods["this_week"].date_to == date(2026, 11, 1)
    assert result.periods["next_week"].date_from == date(2026, 11, 2)
    assert result.periods["next_week"].date_to == date(2026, 11, 8)
