from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.models.enums import ActivationStatus, PaymentStatus


class PurchaseInitializeRequest(BaseModel):
    package_id: uuid.UUID


class PurchaseInitializeResponse(BaseModel):
    reference: str
    authorization_url: str


class PaymentResultResponse(BaseModel):
    reference: str
    payment_status: PaymentStatus
    activation_status: ActivationStatus | None
    plan_name: str


class PaystackWebhookResponse(BaseModel):
    accepted: bool = True
