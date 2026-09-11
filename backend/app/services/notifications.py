from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import Settings
from app.integrations.brevo.client import BrevoEmailSender, EmailDeliveryError
from app.integrations.mnotify import MNotifySmsSender, SmsDeliveryError
from app.models.customer import Customer

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    sms_sent: bool
    email_sent: bool


class CustomerNotificationService:
    """Best-effort customer notifications; provider failures never undo purchases."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(
        self,
        customer: Customer,
        *,
        subject: str,
        message: str,
        send_sms: bool = True,
        send_email: bool = True,
    ) -> DeliveryResult:
        sms_sent = False
        email_sent = False
        if send_sms and customer.phone_number and customer.phone_verified_at is not None:
            try:
                MNotifySmsSender.from_settings(self._settings).send(
                    recipient=customer.phone_number, message=message
                )
                sms_sent = True
            except SmsDeliveryError:
                logger.exception("SMS notification delivery failed for customer %s", customer.id)
        if send_email:
            try:
                BrevoEmailSender.from_settings(self._settings).send_message(
                    recipient=customer.email, subject=subject, message=message
                )
                email_sent = True
            except EmailDeliveryError:
                logger.exception("Email notification delivery failed for customer %s", customer.id)
        return DeliveryResult(sms_sent=sms_sent, email_sent=email_sent)

    def send_bundle_activated(
        self,
        customer: Customer,
        package_name: str,
        *,
        send_email: bool = True,
    ) -> DeliveryResult:
        return self.send(
            customer,
            subject="Your Vlad WiFi bundle is active",
            message=(
                f"Hello {customer.username}, your {package_name} bundle has been activated "
                "successfully. You can now connect to Vlad WiFi."
            ),
            send_sms=False,
            send_email=send_email,
        )
