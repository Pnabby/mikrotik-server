"""Brevo transactional email integration."""

from app.integrations.brevo.client import BrevoEmailSender, EmailDeliveryError

__all__ = ["BrevoEmailSender", "EmailDeliveryError"]
