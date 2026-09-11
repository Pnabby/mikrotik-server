from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import PaymentStatus


class DashboardRevenue(BaseModel):
    today: dict[str, Decimal]
    month: dict[str, Decimal]
    all_time: dict[str, Decimal]
    successful_payments_today: int
    successful_payments_month: int
    pending_payments: int


class DashboardRouterStatus(BaseModel):
    router_id: str
    name: str
    reachable: bool
    active_users: int
    active_devices: int
    error: str | None = None


class DashboardTransaction(BaseModel):
    reference: str
    customer: str
    package: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    occurred_at: datetime


class AdminDashboardResponse(BaseModel):
    generated_at: datetime
    router_id: str | None
    total_users: int
    active_account_users: int
    active_users: int
    active_devices: int
    active_subscriptions: int
    revenue: DashboardRevenue
    routers: list[DashboardRouterStatus]
    recent_transactions: list[DashboardTransaction]

