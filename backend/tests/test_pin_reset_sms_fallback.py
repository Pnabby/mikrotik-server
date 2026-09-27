import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.enums import OtpPurpose
from app.schemas.account import PinResetSmsRequest
from app.services.pin_management import PinManagementService


def _settings() -> Settings:
    return Settings(
        otp_hash_secret="a-secure-test-secret-that-is-at-least-32-characters",
        otp_code_ttl_seconds=600,
        otp_resend_cooldown_seconds=60,
    )


def _challenge(*, phone_number: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        email="user@example.com",
        phone_number=phone_number,
        purpose=OtpPurpose.PIN_RESET,
        code_hash="email-code-hash",
        attempt_count=2,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        consumed_at=None,
    )


def test_sms_fallback_replaces_email_code_for_verified_phone() -> None:
    challenge = _challenge()
    customer = SimpleNamespace(
        phone_number="+233201234567",
        phone_verified_at=datetime.now(UTC),
    )
    session = Mock()
    session.scalar.return_value = challenge
    session.get.return_value = customer
    sender = Mock()
    request = PinResetSmsRequest(
        challenge_id=challenge.id,
        email=challenge.email,
    )

    result = PinManagementService(session, _settings()).send_reset_sms(request, sender)

    assert challenge.phone_number == customer.phone_number
    assert challenge.code_hash != "email-code-hash"
    assert challenge.attempt_count == 0
    assert result.challenge_id == challenge.id
    assert result.destination == "+233*****567"
    sender.send_pin_reset_otp.assert_called_once()
    session.commit.assert_called_once()


def test_sms_fallback_requires_a_verified_phone() -> None:
    challenge = _challenge()
    session = Mock()
    session.scalar.return_value = challenge
    session.get.return_value = SimpleNamespace(
        phone_number="+233201234567",
        phone_verified_at=None,
    )

    with pytest.raises(ServiceError) as raised:
        PinManagementService(session, _settings()).send_reset_sms(
            PinResetSmsRequest(challenge_id=challenge.id, email=challenge.email),
            Mock(),
        )

    assert raised.value.status_code == status.HTTP_409_CONFLICT
    session.commit.assert_not_called()


def test_sms_fallback_can_only_be_used_once_per_email_challenge() -> None:
    challenge = _challenge(phone_number="+233201234567")
    session = Mock()
    session.scalar.return_value = challenge

    with pytest.raises(ServiceError) as raised:
        PinManagementService(session, _settings()).send_reset_sms(
            PinResetSmsRequest(challenge_id=challenge.id, email=challenge.email),
            Mock(),
        )

    assert raised.value.status_code == status.HTTP_409_CONFLICT
    session.get.assert_not_called()
    session.commit.assert_not_called()
