from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.security import PinHasher, PinHashingError
from app.integrations.brevo.client import EmailDeliveryError, OtpEmailSender
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.models.customer import Customer
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import AccountStatus, OtpPurpose
from app.models.router import Router
from app.schemas.registration import RegistrationCompleteRequest, RegistrationStartRequest

logger = logging.getLogger(__name__)
REGISTRATION_COMMENT_PREFIX = "flint-registration="
SIGNUP_UNAVAILABLE_DETAIL = (
    "Signup is currently unavailable. Please contact help and support."
)


@dataclass(frozen=True, slots=True)
class StartedRegistrationOtp:
    challenge_id: uuid.UUID
    destination: str
    expires_in_seconds: int
    resend_after_seconds: int


@dataclass(frozen=True, slots=True)
class CompletedRegistration:
    customer_id: uuid.UUID
    username: str
    account_status: AccountStatus
    router_user_disabled: bool


@dataclass(frozen=True, slots=True)
class UsernameAvailability:
    username: str
    available: bool
    suggestions: list[str]


class RegistrationRouterClient(Protocol):
    def get_hotspot_user(self, username: str) -> dict[str, str] | None: ...

    def get_hotspot_user_profile(self, profile: str) -> dict[str, str] | None: ...

    def create_hotspot_user(
        self,
        *,
        username: str,
        password: str,
        profile: str,
        comment: str,
        disabled: bool = True,
    ) -> None: ...

    def remove_hotspot_user(self, username: str, *, expected_comment: str) -> bool: ...


class RegistrationAvailabilityService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def check_username(self, username: str) -> UsernameAvailability:
        is_taken = self._session.scalar(
            select(Customer.id).where(Customer.username == username).limit(1)
        )
        if is_taken is None:
            return UsernameAvailability(
                username=username,
                available=True,
                suggestions=[],
            )

        suffix_digits = 4
        candidates: list[str] = []
        candidate_set: set[str] = set()
        attempts = 0
        while len(candidates) < 32 and attempts < 128:
            attempts += 1
            suffix = secrets.randbelow(9_000) + 1_000
            candidate = f"{username[: 64 - suffix_digits]}{suffix}"
            if candidate not in candidate_set:
                candidate_set.add(candidate)
                candidates.append(candidate)

        taken_usernames = set(
            self._session.scalars(
                select(Customer.username).where(Customer.username.in_(candidates))
            )
        )
        suggestions = [
            candidate for candidate in candidates if candidate not in taken_usernames
        ][:3]
        return UsernameAvailability(
            username=username,
            available=False,
            suggestions=suggestions,
        )


class RegistrationRouterReadinessService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check(self, router_client: RegistrationRouterClient, username: str) -> None:
        profile = self._settings.mikrotik_registration_profile.strip()
        if not profile:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                SIGNUP_UNAVAILABLE_DETAIL,
            )
        try:
            router_profile = router_client.get_hotspot_user_profile(profile)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            ) from exc
        if router_profile is None:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            )

        try:
            router_user = router_client.get_hotspot_user(username)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            ) from exc
        if router_user is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "That username already exists on the selected router.",
            )


class RegistrationOtpService:
    def __init__(
        self,
        session: Session,
        sender: OtpEmailSender,
        settings: Settings,
    ) -> None:
        self._session = session
        self._sender = sender
        self._settings = settings

    def start(
        self,
        request: RegistrationStartRequest,
        router_client: RegistrationRouterClient,
        *,
        requested_ip: str | None,
    ) -> StartedRegistrationOtp:
        secret = self._hash_secret()
        try:
            get_router(self._session, request.router_id)
        except UnknownRouterError as exc:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.") from exc

        existing_customer = self._session.scalar(
            select(Customer.id).where(
                or_(Customer.email == request.email, Customer.username == request.username)
            )
        )
        if existing_customer is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "An account already uses that email address or username.",
            )

        now = datetime.now(UTC)
        self._enforce_request_limits(request.email, requested_ip=requested_ip, now=now)
        RegistrationRouterReadinessService(self._settings).check(
            router_client,
            request.username,
        )

        challenge_id = uuid.uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = now + timedelta(seconds=self._settings.otp_code_ttl_seconds)

        self._session.execute(
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.email == request.email,
                EmailOtpChallenge.purpose == OtpPurpose.REGISTRATION,
                EmailOtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        challenge = EmailOtpChallenge(
            id=challenge_id,
            email=request.email,
            purpose=OtpPurpose.REGISTRATION,
            code_hash=self._hash_code(secret, challenge_id, code),
            attempt_count=0,
            max_attempts=self._settings.otp_max_attempts,
            expires_at=expires_at,
            requested_ip=requested_ip,
        )
        self._session.add(challenge)
        self._session.commit()

        try:
            self._sender.send_registration_otp(
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
                "Verification email could not be sent.",
            ) from exc

        return StartedRegistrationOtp(
            challenge_id=challenge_id,
            destination=_mask_email(request.email),
            expires_in_seconds=self._settings.otp_code_ttl_seconds,
            resend_after_seconds=self._settings.otp_resend_cooldown_seconds,
        )

    def complete(
        self,
        request: RegistrationCompleteRequest,
        router_client: RegistrationRouterClient,
        pin_hasher: PinHasher,
    ) -> CompletedRegistration:
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
            or challenge.purpose != OtpPurpose.REGISTRATION
        ):
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")

        supplied_hash = self._hash_code(
            secret,
            challenge.id,
            request.code.get_secret_value(),
        )
        code_matches = hmac.compare_digest(challenge.code_hash, supplied_hash)
        if challenge.consumed_at is not None:
            completed = self._completed_registration(challenge, request, code_matches)
            if completed is not None:
                return completed
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid verification code.")

        if now >= _as_utc(challenge.expires_at):
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Verification code has expired.")

        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(status.HTTP_429_TOO_MANY_REQUESTS, "Too many code attempts.")

        if not code_matches:
            challenge.attempt_count += 1
            attempts_exhausted = challenge.attempt_count >= challenge.max_attempts
            if attempts_exhausted:
                challenge.consumed_at = now
            self._session.commit()
            raise ServiceError(
                status.HTTP_429_TOO_MANY_REQUESTS
                if attempts_exhausted
                else status.HTTP_400_BAD_REQUEST,
                "Too many code attempts."
                if attempts_exhausted
                else "Invalid verification code.",
            )

        try:
            get_router(self._session, request.router_id)
        except UnknownRouterError as exc:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.") from exc

        existing_customer = self._session.scalar(
            select(Customer).where(
                or_(Customer.email == request.email, Customer.username == request.username)
            )
        )
        if existing_customer is not None:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "An account already uses that email address or username.",
            )

        database_router = self._session.get(Router, request.router_id)
        if database_router is None or not database_router.is_active:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router is not configured.")

        profile = self._settings.mikrotik_registration_profile.strip()
        if not profile:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                SIGNUP_UNAVAILABLE_DETAIL,
            )
        if self._read_router_profile(router_client, profile) is None:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            )

        marker = f"{REGISTRATION_COMMENT_PREFIX}{challenge.id}"
        router_user = self._read_router_user(router_client, request.username)
        if router_user is not None and router_user.get("comment") != marker:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "That username already exists on the selected router.",
            )

        if router_user is None:
            try:
                router_client.create_hotspot_user(
                    username=request.username,
                    password=request.pin.get_secret_value(),
                    profile=profile,
                    comment=marker,
                    disabled=True,
                )
            except Exception:  # noqa: BLE001 - RouterOS/socket failures share no stable base class.
                # A timeout can happen after RouterOS applied the write. Read back before
                # deciding that creation failed so a retry remains safe.
                try:
                    router_user = self._read_router_user(router_client, request.username)
                except ServiceError:
                    self._compensate_router_user(router_client, request.username, marker)
                    raise
                if router_user is None:
                    raise ServiceError(
                        status.HTTP_502_BAD_GATEWAY,
                        "Router user could not be created.",
                    ) from None
            else:
                try:
                    router_user = self._read_router_user(router_client, request.username)
                except ServiceError:
                    self._compensate_router_user(router_client, request.username, marker)
                    raise

        if router_user is not None and router_user.get("comment") != marker:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "That username already exists on the selected router.",
            )
        if not _router_user_matches(
            router_user,
            username=request.username,
            profile=profile,
            marker=marker,
        ):
            self._compensate_router_user(router_client, request.username, marker)
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "Router user could not be verified.",
            )

        try:
            pin_hash = pin_hasher.hash(request.pin.get_secret_value())
        except PinHashingError as exc:
            self._compensate_router_user(router_client, request.username, marker)
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "PIN could not be secured.",
            ) from exc

        customer = Customer(
            id=uuid.uuid4(),
            router=database_router,
            email=request.email,
            username=request.username,
            pin_hash=pin_hash,
            account_status=AccountStatus.INACTIVE,
            email_verified_at=now,
            mikrotik_user_verified_at=now,
        )
        challenge.customer = customer
        challenge.verified_at = now
        challenge.consumed_at = now
        self._session.add(customer)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            self._compensate_router_user(router_client, request.username, marker)
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "The account could not be created because it already exists.",
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            self._compensate_router_user(router_client, request.username, marker)
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The account could not be saved.",
            ) from exc

        return CompletedRegistration(
            customer_id=customer.id,
            username=customer.username,
            account_status=customer.account_status,
            router_user_disabled=True,
        )

    def _completed_registration(
        self,
        challenge: EmailOtpChallenge,
        request: RegistrationCompleteRequest,
        code_matches: bool,
    ) -> CompletedRegistration | None:
        if not code_matches or challenge.customer_id is None:
            return None
        customer = self._session.get(Customer, challenge.customer_id)
        if (
            customer is None
            or customer.email != request.email
            or customer.username != request.username
            or customer.router_id != request.router_id
        ):
            return None
        return CompletedRegistration(
            customer_id=customer.id,
            username=customer.username,
            account_status=customer.account_status,
            router_user_disabled=True,
        )

    @staticmethod
    def _read_router_user(
        router_client: RegistrationRouterClient, username: str
    ) -> dict[str, str] | None:
        try:
            return router_client.get_hotspot_user(username)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            ) from exc

    @staticmethod
    def _read_router_profile(
        router_client: RegistrationRouterClient, profile: str
    ) -> dict[str, str] | None:
        try:
            return router_client.get_hotspot_user_profile(profile)
        except Exception as exc:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                SIGNUP_UNAVAILABLE_DETAIL,
            ) from exc

    @staticmethod
    def _compensate_router_user(
        router_client: RegistrationRouterClient, username: str, marker: str
    ) -> None:
        removed = False
        try:
            removed = router_client.remove_hotspot_user(
                username,
                expected_comment=marker,
            )
        except Exception:  # noqa: BLE001 - compensation must not hide the original failure.
            logger.critical(
                "RouterOS registration rollback call failed; marker=%s",
                marker,
            )
            return
        if not removed:
            logger.critical(
                "Could not confirm registration rollback on RouterOS; marker=%s",
                marker,
            )

    def _enforce_request_limits(
        self, email: str, *, requested_ip: str | None, now: datetime
    ) -> None:
        latest_created_at = self._session.scalar(
            select(EmailOtpChallenge.created_at)
            .where(
                EmailOtpChallenge.email == email,
                EmailOtpChallenge.purpose == OtpPurpose.REGISTRATION,
            )
            .order_by(EmailOtpChallenge.created_at.desc())
            .limit(1)
        )
        if latest_created_at is not None:
            elapsed = (now - _as_utc(latest_created_at)).total_seconds()
            if elapsed < self._settings.otp_resend_cooldown_seconds:
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
                EmailOtpChallenge.purpose == OtpPurpose.REGISTRATION,
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
                "Email verification is not configured.",
            )
        secret = self._settings.otp_hash_secret.get_secret_value()
        if len(secret) < 32:
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Email verification is not configured.",
            )
        return secret.encode("utf-8")

    @staticmethod
    def _hash_code(secret: bytes, challenge_id: uuid.UUID, code: str) -> str:
        digest = hmac.new(
            secret,
            f"registration:{challenge_id}:{code}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"hmac-sha256${digest}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _mask_email(email: str) -> str:
    local, domain = email.split("@", 1)
    visible = local[0]
    return f"{visible}{'*' * max(2, len(local) - 1)}@{domain}"


def _router_user_matches(
    router_user: dict[str, str] | None,
    *,
    username: str,
    profile: str,
    marker: str,
) -> bool:
    if router_user is None:
        return False
    # RouterOS hides HotSpot passwords from ordinary API reads. The remaining fields
    # prove that the marked record from this request exists in the required disabled state.
    return (
        router_user.get("name", "").casefold() == username.casefold()
        and router_user.get("profile") == profile
        and _routeros_bool(router_user.get("disabled"))
        and router_user.get("comment") == marker
    )


def _routeros_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return isinstance(value, str) and value.strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
