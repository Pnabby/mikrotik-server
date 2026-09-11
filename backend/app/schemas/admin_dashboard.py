from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import AccountStatus, ActivationStatus, PaymentStatus, SubscriptionStatus


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


class AdminTransactionDetail(BaseModel):
    reference: str
    customer_username: str
    customer_email: str
    customer_phone: str | None
    hostel_id: str
    hostel_name: str
    package: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider_status: str | None
    activation_status: ActivationStatus | None
    occurred_at: datetime
    paid_at: datetime | None


class AdminTransactionListResponse(BaseModel):
    generated_at: datetime
    total: int
    offset: int
    limit: int
    revenue: dict[str, Decimal]
    successful: int
    pending: int
    failed: int
    transactions: list[AdminTransactionDetail]


class AdminCustomerDetail(BaseModel):
    id: str
    username: str
    email: str
    phone_number: str | None
    phone_verified: bool
    hostel_id: str
    hostel_name: str
    account_status: AccountStatus
    subscription_status: SubscriptionStatus | None
    current_plan: str | None
    is_online: bool
    connected_devices: int
    joined_at: datetime
    last_login_at: datetime | None
    last_activity_at: datetime


class AdminConnectedDevice(BaseModel):
    session_id: str
    username: str
    customer_email: str | None
    hostel_id: str
    hostel_name: str
    ip_address: str | None
    mac_address: str | None
    uptime: str | None
    login_method: str | None


class AdminCustomerDirectoryResponse(BaseModel):
    generated_at: datetime
    total_users: int
    matched_users: int
    active_subscriptions: int
    online_users: int
    active_devices: int
    unavailable_routers: list[str]
    customers: list[AdminCustomerDetail]
    devices: list[AdminConnectedDevice]


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


class AdminBroadcastRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    subject: str
    message: str
    router_id: str | None = None

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, value: str) -> str:
        if not value or len(value) > 120:
            raise ValueError("Subject must contain between 1 and 120 characters.")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value or len(value) > 1000:
            raise ValueError("Message must contain between 1 and 1000 characters.")
        return value


class AdminBroadcastResponse(BaseModel):
    targeted_users: int
    sms_sent: int
    email_sent: int
    sms_failed: int
    email_failed: int
