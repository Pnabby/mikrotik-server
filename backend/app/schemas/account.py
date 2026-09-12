from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator

from app.models.enums import AccountStatus, ActivationStatus, PaymentStatus, SubscriptionStatus
from app.schemas.registration import PIN_PATTERN, normalize_phone_number, normalize_username


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


class PhoneVerificationStartRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return normalize_phone_number(value)


class PhoneVerificationStartResponse(BaseModel):
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


class PhoneVerificationCompleteRequest(PhoneVerificationStartRequest):
    challenge_id: uuid.UUID
    code: SecretStr

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter exactly six digits.")
        return value


class PhoneVerificationResponse(BaseModel):
    verified: bool = True
    redirect_to: str = "/account"


class LogoutResponse(BaseModel):
    logged_out: bool = True


def normalize_customer_email(value: str) -> str:
    normalized = value.strip().casefold()
    local, separator, domain = normalized.partition("@")
    if (
        not separator
        or not local
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
        or len(normalized) > 320
    ):
        raise ValueError("Enter a valid email address.")
    return normalized


class PinResetStartRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_customer_email(value)


class PinResetStartResponse(BaseModel):
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


class UsernameRecoveryCompleteRequest(BaseModel):
    challenge_id: uuid.UUID
    email: str
    code: SecretStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_customer_email(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter exactly six digits.")
        return value


class UsernameRecoveryResponse(BaseModel):
    username: str


class AccountUnlockStartRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)


class AccountUnlockCompleteRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    challenge_id: uuid.UUID
    username: str
    code: SecretStr

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter exactly six digits.")
        return value


class AccountUnlockResponse(BaseModel):
    unlocked: bool = True


class PinResetCompleteRequest(BaseModel):
    challenge_id: uuid.UUID
    email: str
    code: SecretStr
    new_pin: SecretStr
    new_pin_confirmation: SecretStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_customer_email(value)

    @field_validator("code", "new_pin", "new_pin_confirmation")
    @classmethod
    def validate_six_digits(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter exactly six digits.")
        return value

    @model_validator(mode="after")
    def pins_match(self) -> PinResetCompleteRequest:
        if self.new_pin.get_secret_value() != self.new_pin_confirmation.get_secret_value():
            raise ValueError("PIN confirmation does not match.")
        return self


class ChangePinRequest(BaseModel):
    old_pin: SecretStr
    new_pin: SecretStr
    new_pin_confirmation: SecretStr

    @field_validator("old_pin", "new_pin", "new_pin_confirmation")
    @classmethod
    def validate_six_digits(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter exactly six digits.")
        return value

    @model_validator(mode="after")
    def validate_new_pin(self) -> ChangePinRequest:
        old_pin = self.old_pin.get_secret_value()
        new_pin = self.new_pin.get_secret_value()
        if new_pin != self.new_pin_confirmation.get_secret_value():
            raise ValueError("PIN confirmation does not match.")
        if new_pin == old_pin:
            raise ValueError("Choose a different PIN.")
        return self


class ChangePinResponse(BaseModel):
    changed: bool = True


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


class HostelTransferRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    destination_router_id: str
    pin: SecretStr

    @field_validator("destination_router_id")
    @classmethod
    def validate_destination_router_id(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("Select a valid hostel.")
        return value

    @field_validator("pin")
    @classmethod
    def validate_transfer_pin(cls, value: SecretStr) -> SecretStr:
        if not PIN_PATTERN.fullmatch(value.get_secret_value()):
            raise ValueError("Enter your 6-digit PIN.")
        return value


class HostelTransferResponse(BaseModel):
    transferred: bool = True
    router_id: str
    hostel_name: str
    remaining_data_limit_bytes: int | None


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
    group_id: uuid.UUID | None
    group_name: str | None
    group_description: str | None
    group_display_order: int | None
    group_sort_by_price: bool


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
    phone_number: str | None
    phone_verified: bool
    router_id: str
    hostel_name: str
    account_status: AccountStatus
    current_plan: CurrentPlanResponse | None
    available_plans: list[AvailablePlanResponse]
    previous_plans: list[PreviousPlanResponse]
    purchases: list[PurchaseHistoryResponse]
