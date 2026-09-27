from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.models.enums import AccountStatus, ActivationStatus, PaymentStatus, SubscriptionStatus


class DashboardRevenue(BaseModel):
    today: dict[str, Decimal]
    month: dict[str, Decimal]
    all_time: dict[str, Decimal]
    successful_payments_today: int
    successful_payments_month: int
    pending_payments: int


class AnalyticsDailyPoint(BaseModel):
    date: date
    revenue: dict[str, Decimal]
    successful_sales: int
    new_customers: int


class DashboardRouterStatus(BaseModel):
    router_id: str
    name: str
    reachable: bool
    total_users: int = 0
    active_users: int
    active_devices: int
    active_subscriptions: int
    error: str | None = None


class AdminAccessPointStatus(BaseModel):
    ip_address: str
    online: bool
    configured_mac: str | None = None
    active_mac: str | None = None
    host_name: str | None = None
    comment: str | None = None
    connected_port: str | None = None
    lease_status: str | None = None
    last_seen: str | None = None
    expires_after: str | None = None


class AdminAccessPointListResponse(BaseModel):
    generated_at: datetime
    router_id: str
    hostel_name: str
    network: str
    router_reachable: bool
    error: str | None = None
    online_count: int
    offline_count: int
    access_points: list[AdminAccessPointStatus]


class AdminNetworkUsageResponse(BaseModel):
    generated_at: datetime
    router_id: str
    hostel_name: str
    interface_name: str
    router_reachable: bool
    interface_running: bool
    error: str | None = None
    download_bps: int
    upload_bps: int
    total_download_bytes: int
    total_upload_bytes: int
    total_usage_bytes: int


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


class AdminPlanRevenue(BaseModel):
    profile: str
    display_name: str
    currency: str
    successful_revenue: Decimal
    successful_sales: int
    hostel_count: int
    revenue_share_percent: float


class AdminHostelRevenue(BaseModel):
    hostel_id: str
    hostel_name: str
    revenue: dict[str, Decimal]
    successful_sales: int


class AdminHostelAnalytics(AdminHostelRevenue):
    total_users: int


class RouterHourlyProfilePoint(BaseModel):
    hour: int
    label: str
    samples: int
    average_devices: float
    peak_devices: int
    average_cpu_percent: float
    average_memory_percent: float
    average_download_bps: float
    average_upload_bps: float
    predicted_peak: bool


class RouterTimelinePoint(BaseModel):
    start: datetime
    end: datetime
    label: str
    samples: int
    observations: int
    lowest_devices: float
    average_devices: float
    highest_devices: float
    peak_devices: int
    lowest_cpu_percent: float
    average_cpu_percent: float
    highest_cpu_percent: float
    lowest_memory_percent: float
    average_memory_percent: float
    highest_memory_percent: float
    lowest_download_bps: float
    average_download_bps: float
    highest_download_bps: float
    lowest_upload_bps: float
    average_upload_bps: float
    highest_upload_bps: float
    lowest_interface_availability_percent: float
    interface_availability_percent: float
    highest_interface_availability_percent: float


class RouterPerformanceSummary(BaseModel):
    router_id: str | None = None
    router_name: str
    successful_samples: int
    failed_samples: int
    average_devices: float
    peak_devices: int
    average_cpu_percent: float
    peak_cpu_percent: float
    average_memory_percent: float
    peak_memory_percent: float
    average_free_memory_bytes: float
    average_download_bps: float
    peak_download_bps: int
    average_upload_bps: float
    peak_upload_bps: int
    downloaded_bytes: int
    uploaded_bytes: int
    interface_availability_percent: float
    collection_success_percent: float
    current_uptime_seconds: int
    restart_count: int
    average_temperature: float | None = None
    average_voltage: float | None = None


class AdminRouterAnalytics(BaseModel):
    available: bool
    period_hours: int
    collection_started_at: datetime | None = None
    last_collected_at: datetime | None = None
    baseline_days: int
    prediction_ready: bool
    days_until_prediction: int
    predicted_peak_hours: list[int]
    summary: RouterPerformanceSummary | None = None
    hourly_profile: list[RouterHourlyProfilePoint]
    timeline: list[RouterTimelinePoint]
    routers: list[RouterPerformanceSummary]


class AdminAnalyticsResponse(BaseModel):
    generated_at: datetime
    router_id: str | None
    period_days: int
    comparison_available: bool
    date_from: date
    date_to: date
    primary_currency: str
    revenue: dict[str, Decimal]
    previous_revenue: dict[str, Decimal]
    average_order_value: dict[str, Decimal]
    successful_sales: int
    previous_successful_sales: int
    pending_payments: int
    failed_payments: int
    success_rate: float
    new_customers: int
    previous_new_customers: int
    total_customers: int
    daily: list[AnalyticsDailyPoint]
    plan_performance: list[AdminPlanRevenue]
    hostel_performance: list[AdminHostelAnalytics]
    router_analytics: AdminRouterAnalytics


class AdminTransactionListResponse(BaseModel):
    generated_at: datetime
    total: int
    offset: int
    limit: int
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


class AdminCustomerDeleteRequest(BaseModel):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        if not 8 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Enter your admin password.")
        return value


class AdminCustomerDeleteResponse(BaseModel):
    deleted: bool = True


class AdminCustomerTransferRequest(AdminCustomerDeleteRequest):
    model_config = ConfigDict(str_strip_whitespace=True)

    destination_router_id: str

    @field_validator("destination_router_id")
    @classmethod
    def validate_destination_router_id(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("Select a valid hostel.")
        return value


class AdminCustomerTransferResponse(BaseModel):
    transferred: bool = True
    router_id: str
    hostel_name: str
    remaining_data_limit_bytes: int | None


class AdminDashboardResponse(BaseModel):
    generated_at: datetime
    router_id: str | None
    total_users: int
    active_account_users: int
    active_users: int
    active_devices: int
    active_subscriptions: int
    revenue: DashboardRevenue
    revenue_last_7_days: list[AnalyticsDailyPoint]
    routers: list[DashboardRouterStatus]


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
