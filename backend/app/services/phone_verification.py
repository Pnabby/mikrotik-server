from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.integrations.mnotify import MNotifySmsSender, SmsDeliveryError
from app.models.customer import Customer
from app.models.enums import OtpFlow
from app.models.phone_otp_challenge import PhoneOtpChallenge
from app.services.otp_limits import customer_subject, enforce_otp_request_limit


@dataclass(frozen=True, slots=True)
class StartedPhoneOtp:
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


class PhoneVerificationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def start(
        self, customer: Customer, phone_number: str, *, requested_ip: str | None
    ) -> StartedPhoneOtp:
        if customer.phone_verified_at is not None:
            raise ServiceError(status.HTTP_409_CONFLICT, "Phone number is already verified.")
        owner = self._session.scalar(
            select(Customer.id).where(
                Customer.phone_number == phone_number, Customer.id != customer.id
            )
        )
        if owner is not None:
            raise ServiceError(status.HTTP_409_CONFLICT, "Phone number is already registered.")
        now = datetime.now(UTC)
        enforce_otp_request_limit(
            self._session, self._settings, OtpFlow.PHONE_VERIFICATION,
            customer_subject(customer.id), now=now,
        )

        challenge_id = uuid.uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._session.execute(
            update(PhoneOtpChallenge)
            .where(
                PhoneOtpChallenge.customer_id == customer.id,
                PhoneOtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        challenge = PhoneOtpChallenge(
            id=challenge_id,
            customer_id=customer.id,
            phone_number=phone_number,
            code_hash=self._hash(challenge_id, code),
            max_attempts=self._settings.otp_max_attempts,
            expires_at=now + timedelta(seconds=self._settings.otp_code_ttl_seconds),
            requested_ip=requested_ip,
        )
        self._session.add(challenge)
        self._session.commit()
        try:
            MNotifySmsSender.from_settings(self._settings).send_verification_otp(
                recipient=phone_number,
                code=code,
                expires_in_minutes=max(1, (self._settings.otp_code_ttl_seconds + 59) // 60),
            )
        except SmsDeliveryError as exc:
            challenge.consumed_at = datetime.now(UTC)
            self._session.commit()
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Verification SMS could not be sent."
            ) from exc
        customer.phone_number = phone_number
        self._session.commit()
        return StartedPhoneOtp(
            challenge_id,
            _mask_phone(phone_number),
            self._settings.otp_code_ttl_seconds,
            self._settings.otp_resend_cooldown_seconds,
        )

    def complete(
        self, customer: Customer, challenge_id: uuid.UUID, phone_number: str, code: str
    ) -> None:
        challenge = self._session.scalar(
            select(PhoneOtpChallenge).where(PhoneOtpChallenge.id == challenge_id).with_for_update()
        )
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.customer_id != customer.id
            or challenge.phone_number != phone_number
        ):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if challenge.consumed_at is not None or now >= _as_utc(challenge.expires_at):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Verification code has expired.")
        if not hmac.compare_digest(challenge.code_hash, self._hash(challenge.id, code)):
            challenge.attempt_count += 1
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS
                if challenge.consumed_at
                else status.HTTP_400_BAD_REQUEST,
                "Invalid verification code.",
            )
        customer.phone_number = phone_number
        customer.phone_verified_at = now
        challenge.consumed_at = now
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT, "Phone number is already registered."
            ) from exc

    def _hash(self, challenge_id: uuid.UUID, code: str) -> str:
        if not self._settings.otp_hash_secret:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Phone verification is not configured."
            )
        key = self._settings.otp_hash_secret.get_secret_value().encode()
        return hmac.new(key, f"phone:{challenge_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _mask_phone(phone: str) -> str:
    return f"{phone[:4]}*****{phone[-3:]}"


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
