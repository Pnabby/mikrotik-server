from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.enums import OtpPurpose
from app.schemas.registration import RegistrationStartRequest
from app.services.pin_management import PinManagementService
from app.services.registration import (
    RegistrationOtpService,
    _registration_conflict_fields,
)

NOW = datetime(2026, 9, 11, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(otp_max_requests_per_hour=5)


def test_registration_limit_checks_only_the_destination_email() -> None:
    session = Mock()
    session.scalar.side_effect = [None, 4]
    service = RegistrationOtpService(session, Mock(), _settings())

    service._enforce_request_limits("new-user@example.com", now=NOW)

    assert session.scalar.call_count == 2


def test_registration_limit_still_blocks_repeated_requests_for_one_email() -> None:
    session = Mock()
    session.scalar.side_effect = [None, 5]
    service = RegistrationOtpService(session, Mock(), _settings())

    with pytest.raises(ServiceError) as raised:
        service._enforce_request_limits("same-user@example.com", now=NOW)

    assert raised.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_registration_conflicts_identify_each_used_account_field() -> None:
    session = Mock()
    session.execute.return_value = [
        ("used@example.com", "differentuser", "+233201111111"),
        ("different@example.com", "usedname", "+233202222222"),
    ]
    request = RegistrationStartRequest(
        email="used@example.com",
        phone_number="020 222 2222",
        username="usedname",
        router_id="hall",
        pin="123456",
        accepted_terms=True,
    )

    field_errors = _registration_conflict_fields(session, request)

    assert field_errors == {
        "email": "This email address is already registered.",
        "username": "This username is already taken.",
        "phone_number": "This phone number is already registered.",
    }


def test_account_recovery_limit_checks_only_the_destination_email() -> None:
    session = Mock()
    session.scalar.side_effect = [None, 4]
    service = PinManagementService(session, _settings())

    service._enforce_request_limits(
        "new-user@example.com",
        purpose=OtpPurpose.PIN_RESET,
        now=NOW,
    )

    assert session.scalar.call_count == 2


def test_account_recovery_limit_still_blocks_repeated_requests_for_one_email() -> None:
    session = Mock()
    session.scalar.side_effect = [None, 5]
    service = PinManagementService(session, _settings())

    with pytest.raises(ServiceError) as raised:
        service._enforce_request_limits(
            "same-user@example.com",
            purpose=OtpPurpose.PIN_RESET,
            now=NOW,
        )

    assert raised.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
