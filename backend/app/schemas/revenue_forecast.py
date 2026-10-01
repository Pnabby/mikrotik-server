from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class RevenueForecastPoint(BaseModel):
    date: date
    revenue: Decimal
    lower: Decimal
    upper: Decimal


class RevenueForecastHistoryPoint(BaseModel):
    date: date
    revenue: Decimal


class RevenueForecastHorizon(BaseModel):
    days: int
    date_from: date
    date_to: date
    projected_revenue: Decimal
    lower_revenue: Decimal
    upper_revenue: Decimal
    daily: list[RevenueForecastPoint]


class RevenueForecast(BaseModel):
    currency: str
    available: bool
    reason: str | None = None
    history_days: int
    history_from: date | None = None
    history_to: date | None = None
    recent_daily_average: Decimal = Decimal(0)
    weekly_change_percent: float | None = None
    history: list[RevenueForecastHistoryPoint] = Field(default_factory=list)
    horizons: dict[int, RevenueForecastHorizon] = Field(default_factory=dict)
