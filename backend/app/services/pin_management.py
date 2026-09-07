from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.security import PinHasher, PinHashingError
from app.integrations.brevo.client import EmailDeliveryError, OtpEmailSender
from app.integrations.mikrotik.registry import UnknownRouterError
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.customer_session import CustomerSession
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import AuditActorType, OtpPurpose
from app.schemas.account import (
    AccountUnlockCompleteRequest,
    AccountUnlockStartRequest,
    ChangePinRequest,
    PinResetCompleteRequest,
    PinResetStartRequest,
    UsernameRecoveryCompleteRequest,
)
from app.services.customer_auth import login_attempt_limiter

PASSWORD_SERVICE_UNAVAILABLE = "The hostel router is temporarily unavailable."


class PasswordRouterClient(Protocol):
    def get_hotspot_user(self, username: str) -> dict[str, str] | None: ...

    def change_hotspot_user_password(self, username: str, password: str) -> None: ...

    def disconnect(self) -> None: ...


PasswordRouterClientFactory = Callable[[str], PasswordRouterClient]


@dataclass(frozen=True, slots=True)
class StartedPinReset:
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


class PinManagementService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def start_reset(
        self,
        request: PinResetStartRequest,
        sender: OtpEmailSender,
        router_client_factory: PasswordRouterClientFactory,
        *,
        requested_ip: str | None,
    ) -> StartedPinReset:
        return self._start_recovery(
            request,
            purpose=OtpPurpose.PIN_RESET,
            send_otp=sender.send_pin_reset_otp,
            router_client_factory=router_client_factory,
            requested_ip=requested_ip,
        )

    def start_username_recovery(
        self,
        request: PinResetStartRequest,
        sender: OtpEmailSender,
        router_client_factory: PasswordRouterClientFactory,
        *,
        requested_ip: str | None,
    ) -> StartedPinReset:
        return self._start_recovery(
            request,
            purpose=OtpPurpose.USERNAME_RECOVERY,
            send_otp=sender.send_username_recovery_otp,
            router_client_factory=router_client_factory,
            requested_ip=requested_ip,
        )

    def start_account_unlock(
        self,
        request: AccountUnlockStartRequest,
        sender: OtpEmailSender,
        router_client_factory: PasswordRouterClientFactory,
        *,
        requested_ip: str | None,
    ) -> StartedPinReset:
        secret = self._hash_secret()
        customer = self._session.scalar(
            select(Customer).where(Customer.username == request.username).limit(1)
        )
        if customer is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Account was not found.")
        if customer.locked_at is None:
            raise ServiceError(status.HTTP_409_CONFLICT, "Account is not locked.")

        now = datetime.now(UTC)
        self._enforce_request_limits(
            customer.email,
            purpose=OtpPurpose.ACCOUNT_UNLOCK,
            requested_ip=requested_ip,
            now=now,
        )
        self._check_router(customer, router_client_factory)

        challenge_id = uuid.uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._session.execute(
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.email == customer.email,
                EmailOtpChallenge.purpose == OtpPurpose.ACCOUNT_UNLOCK,
                EmailOtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        challenge = EmailOtpChallenge(
            id=challenge_id,
            customer=customer,
            email=customer.email,
            purpose=OtpPurpose.ACCOUNT_UNLOCK,
            code_hash=self._hash_code(
                secret, challenge_id, code, OtpPurpose.ACCOUNT_UNLOCK
            ),
            attempt_count=0,
            max_attempts=self._settings.otp_max_attempts,
            expires_at=now + timedelta(seconds=self._settings.otp_code_ttl_seconds),
            requested_ip=(requested_ip or "")[:64] or None,
        )
        self._session.add(challenge)
        self._session.commit()
        try:
            sender.send_account_unlock_otp(
                recipient=customer.email,
                code=code,
                expires_in_minutes=max(
                    1, (self._settings.otp_code_ttl_seconds + 59) // 60
                ),
            )
        except EmailDeliveryError as exc:
            challenge.consumed_at = datetime.now(UTC)
            self._session.commit()
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Account unlock email could not be sent.",
            ) from exc

        return StartedPinReset(
            challenge_id=challenge_id,
            destination=_mask_email(customer.email),
            expires_in_seconds=self._settings.otp_code_ttl_seconds,
            resend_after_seconds=self._settings.otp_resend_cooldown_seconds,
        )

    def _start_recovery(
        self,
        request: PinResetStartRequest,
        *,
        purpose: OtpPurpose,
        send_otp: Callable[..., None],
        router_client_factory: PasswordRouterClientFactory,
        requested_ip: str | None,
    ) -> StartedPinReset:
        secret = self._hash_secret()
        now = datetime.now(UTC)
        self._enforce_request_limits(
            request.email,
            purpose=purpose,
            requested_ip=requested_ip,
            now=now,
        )
        customer = self._session.scalar(
            select(Customer).where(Customer.email == request.email).limit(1)
        )

        if customer is not None:
            self._check_router(customer, router_client_factory)

        challenge_id = uuid.uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = now + timedelta(seconds=self._settings.otp_code_ttl_seconds)
        self._session.execute(
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.email == request.email,
                EmailOtpChallenge.purpose == purpose,
                EmailOtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        challenge = EmailOtpChallenge(
            id=challenge_id,
            customer=customer,
            email=request.email,
            purpose=purpose,
            code_hash=self._hash_code(secret, challenge_id, code, purpose),
            attempt_count=0,
            max_attempts=self._settings.otp_max_attempts,
            expires_at=expires_at,
            requested_ip=(requested_ip or "")[:64] or None,
        )
        self._session.add(challenge)
        self._session.commit()

        if customer is not None:
            try:
                send_otp(
                    recipient=request.email,
                    code=code,
                    expires_in_minutes=max(
                        1, (self._settings.otp_code_ttl_seconds + 59) // 60
                    ),
                )
            except EmailDeliveryError as exc:
                challenge.consumed_at = datetime.now(UTC)
                self._session.commit()
                raise ServiceError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Recovery email could not be sent.",
                ) from exc

        return StartedPinReset(
            challenge_id=challenge_id,
            destination=_mask_email(request.email),
            expires_in_seconds=self._settings.otp_code_ttl_seconds,
            resend_after_seconds=self._settings.otp_resend_cooldown_seconds,
        )

    def complete_reset(
        self,
        request: PinResetCompleteRequest,
        pin_hasher: PinHasher,
        router_client_factory: PasswordRouterClientFactory,
        *,
        ip_address: str | None,
    ) -> None:
        secret = self._hash_secret()
        challenge = self._session.scalar(
            select(EmailOtpChallenge)
            .where(EmailOtpChallenge.id == request.challenge_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.email != request.email
            or challenge.purpose != OtpPurpose.PIN_RESET
        ):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if challenge.consumed_at is not None or challenge.customer_id is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if now >= _as_utc(challenge.expires_at):
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Verification code has expired.")
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_429_TOO_MANY_REQUESTS, "Too many code attempts.")

        supplied_hash = self._hash_code(
            secret,
            challenge.id,
            request.code.get_secret_value(),
            OtpPurpose.PIN_RESET,
        )
        if not hmac.compare_digest(challenge.code_hash, supplied_hash):
            challenge.attempt_count += 1
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS
                if challenge.consumed_at is not None
                else status.HTTP_400_BAD_REQUEST,
                "Invalid verification code.",
            )

        customer = self._session.get(Customer, challenge.customer_id)
        if customer is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        new_pin = request.new_pin.get_secret_value()
        new_hash = self._hash_pin(pin_hasher, new_pin)
        client = self._router_client(customer, router_client_factory)
        try:
            self._change_router_pin(client, customer.username, new_pin)
        finally:
            with suppress(Exception):
                client.disconnect()

        customer.pin_hash = new_hash
        customer.last_activity_at = now
        challenge.verified_at = now
        challenge.consumed_at = now
        self._session.execute(
            update(CustomerSession)
            .where(
                CustomerSession.customer_id == customer.id,
                CustomerSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.CUSTOMER,
                customer_id=customer.id,
                action="customer.pin_reset",
                entity_type="customer",
                entity_id=str(customer.id),
                details={"router_id": customer.router_id},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._commit_password_change()

    def complete_username_recovery(
        self,
        request: UsernameRecoveryCompleteRequest,
        router_client_factory: PasswordRouterClientFactory,
        *,
        ip_address: str | None,
    ) -> str:
        challenge = self._session.scalar(
            select(EmailOtpChallenge)
            .where(EmailOtpChallenge.id == request.challenge_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if (
            challenge is None
            or challenge.email != request.email
            or challenge.purpose != OtpPurpose.USERNAME_RECOVERY
        ):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if challenge.consumed_at is not None or challenge.customer_id is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if now >= _as_utc(challenge.expires_at):
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Verification code has expired.")
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_429_TOO_MANY_REQUESTS, "Too many code attempts.")
        supplied_hash = self._hash_code(
            self._hash_secret(),
            challenge.id,
            request.code.get_secret_value(),
            OtpPurpose.USERNAME_RECOVERY,
        )
        if not hmac.compare_digest(challenge.code_hash, supplied_hash):
            challenge.attempt_count += 1
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS
                if challenge.consumed_at is not None
                else status.HTTP_400_BAD_REQUEST,
                "Invalid verification code.",
            )
        customer = self._session.get(Customer, challenge.customer_id)
        if customer is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        self._check_router(customer, router_client_factory)
        challenge.verified_at = now
        challenge.consumed_at = now
        customer.last_activity_at = now
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.CUSTOMER,
                customer_id=customer.id,
                action="customer.username_recovered",
                entity_type="customer",
                entity_id=str(customer.id),
                details={"router_id": customer.router_id},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._commit_password_change()
        return customer.username

    def complete_account_unlock(
        self,
        request: AccountUnlockCompleteRequest,
        router_client_factory: PasswordRouterClientFactory,
        *,
        ip_address: str | None,
    ) -> None:
        challenge = self._session.scalar(
            select(EmailOtpChallenge)
            .where(EmailOtpChallenge.id == request.challenge_id)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if challenge is None or challenge.purpose != OtpPurpose.ACCOUNT_UNLOCK:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if challenge.consumed_at is not None or challenge.customer_id is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        if now >= _as_utc(challenge.expires_at):
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Verification code has expired.")
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_429_TOO_MANY_REQUESTS, "Too many code attempts.")

        customer = self._session.get(Customer, challenge.customer_id)
        if customer is None or customer.username != request.username:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")
        supplied_hash = self._hash_code(
            self._hash_secret(),
            challenge.id,
            request.code.get_secret_value(),
            OtpPurpose.ACCOUNT_UNLOCK,
        )
        if not hmac.compare_digest(challenge.code_hash, supplied_hash):
            challenge.attempt_count += 1
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS
                if challenge.consumed_at is not None
                else status.HTTP_400_BAD_REQUEST,
                "Invalid verification code.",
            )

        self._check_router(customer, router_client_factory)
        customer.failed_login_attempts = 0
        customer.locked_at = None
        customer.last_activity_at = now
        challenge.verified_at = now
        challenge.consumed_at = now
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.CUSTOMER,
                customer_id=customer.id,
                action="customer.account_unlocked",
                entity_type="customer",
                entity_id=str(customer.id),
                details={"router_id": customer.router_id},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Account unlock could not be saved.",
            ) from exc

        login_attempt_limiter.clear_for_username(customer.username)

    def change_pin(
        self,
        customer: Customer,
        request: ChangePinRequest,
        pin_hasher: PinHasher,
        router_client: PasswordRouterClient,
        *,
        current_session_token: str | None,
        ip_address: str | None,
    ) -> None:
        if not pin_hasher.verify(customer.pin_hash, request.old_pin.get_secret_value()):
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Current PIN is incorrect.")
        new_pin = request.new_pin.get_secret_value()
        new_hash = self._hash_pin(pin_hasher, new_pin)
        self._change_router_pin(router_client, customer.username, new_pin)

        now = datetime.now(UTC)
        customer.pin_hash = new_hash
        customer.last_activity_at = now
        revoke_query = update(CustomerSession).where(
            CustomerSession.customer_id == customer.id,
            CustomerSession.revoked_at.is_(None),
        )
        if current_session_token:
            revoke_query = revoke_query.where(
                CustomerSession.token_hash != _hash_session_token(current_session_token)
            )
        self._session.execute(revoke_query.values(revoked_at=now))
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.CUSTOMER,
                customer_id=customer.id,
                action="customer.pin_changed",
                entity_type="customer",
                entity_id=str(customer.id),
                details={"router_id": customer.router_id},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._commit_password_change()

    def _check_router(
        self, customer: Customer, router_client_factory: PasswordRouterClientFactory
    ) -> None:
        client = self._router_client(customer, router_client_factory)
        try:
            self._require_router_user(client, customer.username)
        finally:
            with suppress(Exception):
                client.disconnect()

    @staticmethod
    def _router_client(
        customer: Customer, router_client_factory: PasswordRouterClientFactory
    ) -> PasswordRouterClient:
        try:
            return router_client_factory(customer.router_id)
        except (UnknownRouterError, ValueError) as exc:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                PASSWORD_SERVICE_UNAVAILABLE,
            ) from exc

    @staticmethod
    def _require_router_user(client: PasswordRouterClient, username: str) -> None:
        try:
            router_user = client.get_hotspot_user(username)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                PASSWORD_SERVICE_UNAVAILABLE,
            ) from exc
        if router_user is None:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                PASSWORD_SERVICE_UNAVAILABLE,
            )

    @classmethod
    def _change_router_pin(
        cls, client: PasswordRouterClient, username: str, new_pin: str
    ) -> None:
        cls._require_router_user(client, username)
        try:
            client.change_hotspot_user_password(username, new_pin)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                PASSWORD_SERVICE_UNAVAILABLE,
            ) from exc

    @staticmethod
    def _hash_pin(pin_hasher: PinHasher, pin: str) -> str:
        try:
            return pin_hasher.hash(pin)
        except PinHashingError as exc:
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "PIN could not be secured.",
            ) from exc

    def _commit_password_change(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "PIN change could not be saved.",
            ) from exc

    def _enforce_request_limits(
        self,
        email: str,
        *,
        purpose: OtpPurpose,
        requested_ip: str | None,
        now: datetime,
    ) -> None:
        latest = self._session.scalar(
            select(EmailOtpChallenge.created_at)
            .where(
                EmailOtpChallenge.email == email,
                EmailOtpChallenge.purpose == purpose,
            )
            .order_by(EmailOtpChallenge.created_at.desc())
            .limit(1)
        )
        if latest is not None and (
            now - _as_utc(latest)
        ).total_seconds() < self._settings.otp_resend_cooldown_seconds:
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Please wait before requesting another code.",
            )
        since = now - timedelta(hours=1)
        email_count = self._session.scalar(
            select(func.count())
            .select_from(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.email == email,
                EmailOtpChallenge.purpose == purpose,
                EmailOtpChallenge.created_at >= since,
            )
        )
        ip_count = 0
        if requested_ip:
            ip_count = self._session.scalar(
                select(func.count())
                .select_from(EmailOtpChallenge)
                .where(
                    EmailOtpChallenge.requested_ip == requested_ip,
                    EmailOtpChallenge.created_at >= since,
                )
            )
        if max(email_count or 0, ip_count or 0) >= self._settings.otp_max_requests_per_hour:
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many verification codes requested.",
            )

    def _hash_secret(self) -> bytes:
        if self._settings.otp_hash_secret is None:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "PIN reset is not configured.",
            )
        secret = self._settings.otp_hash_secret.get_secret_value()
        if len(secret) < 32:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "PIN reset is not configured.",
            )
        return secret.encode("utf-8")

    @staticmethod
    def _hash_code(
        secret: bytes,
        challenge_id: uuid.UUID,
        code: str,
        purpose: OtpPurpose,
    ) -> str:
        digest = hmac.new(
            secret,
            f"{purpose.value}:{challenge_id}:{code}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"hmac-sha256${digest}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mask_email(email: str) -> str:
    local, domain = email.split("@", 1)
    return f"{local[0]}{'*' * max(2, len(local) - 1)}@{domain}"


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(f"customer-session:{token}".encode()).hexdigest()
