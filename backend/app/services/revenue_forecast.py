from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import sqrt

from app.schemas.revenue_forecast import (
    RevenueForecast,
    RevenueForecastHistoryPoint,
    RevenueForecastPeriod,
    RevenueForecastPoint,
)


def _money(value: float) -> Decimal:
    return Decimal(str(max(0, value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _next_month_start(value: date) -> date:
    return (value.replace(day=28) + timedelta(days=4)).replace(day=1)


def forecast_revenue(
    *,
    currency: str,
    today: date,
    first_sale_date: date,
    daily_revenue: dict[date, Decimal],
) -> RevenueForecast:
    """Nowcast current calendar periods and forecast their next counterparts.

    Weekday averages describe weekly demand. The latest seven days set the
    current revenue level. Week-over-week movement is capped at +/-25% and
    damped by 10% each day to avoid extrapolating a short-lived spike forever.
    Bounds are illustrative scenarios from historical weekday residuals,
    widened with the horizon. They are not calibrated confidence intervals.
    Today's partial payments are excluded from model fitting, but included in
    actuals and used as a floor for today's full-day prediction. Completed
    dates use known actuals, never retroactively invented predictions.
    """
    end = today - timedelta(days=1)
    start = max(first_sale_date, today - timedelta(days=28))
    count = max(0, (end - start).days + 1)
    history = [
        RevenueForecastHistoryPoint(
            date=start + timedelta(days=index),
            revenue=daily_revenue.get(start + timedelta(days=index), Decimal(0)),
        )
        for index in range(count)
    ]
    result = RevenueForecast(
        currency=currency, available=False, history_days=count,
        history_from=start if count else None, history_to=end if count else None,
        history=history,
    )
    if count < 14:
        result.reason = "At least 14 completed days of paid revenue history are needed."
        return result
    values = [float(point.revenue) for point in history]
    if not any(values):
        result.reason = "No paid revenue was recorded in the last 28 completed days."
        return result

    recent = sum(values[-7:]) / 7
    previous = sum(values[-14:-7]) / 7
    change = (recent / previous - 1) if previous else None
    result.recent_daily_average = _money(recent)
    result.weekly_change_percent = round(change * 100, 1) if change is not None else None
    trend = max(-0.25, min(0.25, change or 0))
    mean = sum(values) / count
    weekday_means = {
        weekday: sum(float(point.revenue) for point in history if point.date.weekday() == weekday)
        / sum(point.date.weekday() == weekday for point in history)
        for weekday in range(7)
    }
    # A minimum spread keeps even a flat short history from implying certainty.
    spread = max(mean * 0.1, sqrt(sum(
        (float(point.revenue) - weekday_means[point.date.weekday()]) ** 2
        for point in history
    ) / (count - 1)))
    week_start = today - timedelta(days=today.weekday())
    next_week = week_start + timedelta(days=7)
    month_start = today.replace(day=1)
    next_month = _next_month_start(today)
    periods = {
        "today": ("Today", today, today),
        "tomorrow": ("Tomorrow", today + timedelta(days=1), today + timedelta(days=1)),
        "this_week": ("This week", week_start, next_week - timedelta(days=1)),
        "next_week": ("Next week", next_week, next_week + timedelta(days=6)),
        "this_month": ("This month", month_start, next_month - timedelta(days=1)),
        "next_month": ("Next month", next_month, _next_month_start(next_month) - timedelta(days=1)),
    }

    def point_for(target: date) -> RevenueForecastPoint:
        actual = daily_revenue.get(target, Decimal(0)) if target <= today else None
        if target < today:
            return RevenueForecastPoint(
                date=target, revenue=actual, lower=actual, upper=actual,
                actual_revenue=actual, is_prediction=False,
            )
        days_since_history = (target - end).days
        damped_days = (1 - 0.9 ** days_since_history) / (1 - 0.9)
        level = recent * (weekday_means[target.weekday()] / mean)
        estimate = max(0, level * (1 + trend * damped_days / 7))
        width = spread * sqrt(1 + days_since_history / 7)
        actual_floor = actual or Decimal(0)
        return RevenueForecastPoint(
            date=target, revenue=max(actual_floor, _money(estimate)),
            lower=max(actual_floor, _money(estimate - width)),
            upper=max(actual_floor, _money(estimate + width)), actual_revenue=actual,
        )

    result.available = True
    for key, (label, period_start, period_end) in periods.items():
        days = (period_end - period_start).days + 1
        points = [point_for(period_start + timedelta(days=index)) for index in range(days)]
        result.periods[key] = RevenueForecastPeriod(
            label=label, days=days, date_from=period_start, date_to=period_end,
            projected_revenue=sum((point.revenue for point in points), Decimal(0)),
            lower_revenue=sum((point.lower for point in points), Decimal(0)),
            upper_revenue=sum((point.upper for point in points), Decimal(0)),
            actual_revenue=sum((point.actual_revenue or Decimal(0) for point in points), Decimal(0))
            if period_start <= today else None,
            daily=points,
        )
    return result
