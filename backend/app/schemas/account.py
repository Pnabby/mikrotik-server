from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.models.enums import AccountStatus, ActivationStatus, PaymentStatus, SubscriptionStatus
from app.schemas.registration import PIN_PATTERN, normalize_username


class CustomerLoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str
    pin: SecretStr
    remember_me: bool = False

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter a valid PIN.")
        return value


class AuthenticatedCustomerResponse(BaseModel):
    username: str
    redirect_to: str = "/account"


class LogoutResponse(BaseModel):
    logged_out: bool = True


class DeleteAccountRequest(BaseModel):
    pin: SecretStr

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter your 6-digit PIN.")
        return value


class DeleteAccountResponse(BaseModel):
    deleted: bool = True


class CurrentPlanResponse(BaseModel):
    name: str
    status: SubscriptionStatus
    starts_at: datetime | None
    expires_at: datetime | None
    duration_seconds: int | None
    data_limit_bytes: int | None
    device_limit: int | None
    download_speed: str | None


class AvailablePlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    amount: Decimal
    currency: str
    duration_seconds: int | None
    data_limit_bytes: int | None
    device_limit: int | None
    download_speed: str | None
    is_promotional: bool
    promo_claimed: bool
    purchase_available: bool


class PreviousPlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: SubscriptionStatus
    purchased_at: datetime
    starts_at: datetime | None
    expires_at: datetime | None
    ended_at: datetime | None


class PurchaseHistoryResponse(BaseModel):
    reference: str
    plan_name: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    activation_status: ActivationStatus | None
    purchased_at: datetime
    paid_at: datetime | None


class CustomerAccountResponse(BaseModel):
    username: str
    email: str
    hostel_name: str
    account_status: AccountStatus
    current_plan: CurrentPlanResponse | None
    available_plans: list[AvailablePlanResponse]
    previous_plans: list[PreviousPlanResponse]
    purchases: list[PurchaseHistoryResponse]
