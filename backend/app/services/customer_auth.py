from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.security import PinHasher, PinHashingError
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.customer_session import CustomerSession
from app.models.enums import AccountStatus, AuditActorType
from app.schemas.account import CustomerLoginRequest

CUSTOMER_SESSION_COOKIE = "flint_customer_session"
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60


class LoginAttemptLimiter:
    def __init__(self) -> None:
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def enforce(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            attempts = self._attempts[key]
            while attempts and now - attempts[0] >= _LOGIN_ATTEMPT_WINDOW_SECONDS:
                attempts.popleft()
            if len(attempts) >= _LOGIN_ATTEMPT_LIMIT:
                raise ServiceError(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    "Too many login attempts.",
                )

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear_for_username(self, username: str) -> None:
        suffix = f":{username}"
        with self._lock:
            for key in tuple(self._attempts):
                if key.endswith(suffix):
                    self._attempts.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()


@dataclass(frozen=True, slots=True)
class CreatedCustomerSession:
    customer: Customer
    token: str
    expires_at: datetime
    persistent: bool


class CustomerAuthenticationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def login(
        self,
        request: CustomerLoginRequest,
        pin_hasher: PinHasher,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CreatedCustomerSession:
        attempt_key = f"{ip_address or 'unknown'}:{request.username}"
        customer = self._session.scalar(
            select(Customer)
            .where(Customer.username == request.username)
            .with_for_update()
            .limit(1)
        )
        pin = request.pin.get_secret_value()
        if customer is None:
            login_attempt_limiter.enforce(attempt_key)
            try:
                pin_hasher.hash(pin)
            except PinHashingError:
                pass
            login_attempt_limiter.record_failure(attempt_key)
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Invalid username or PIN.")
        if customer.locked_at is not None:
            raise ServiceError(status.HTTP_423_LOCKED, "Account is locked.")
        if not pin_hasher.verify(customer.pin_hash, pin):
            customer.failed_login_attempts += 1
            locked = customer.failed_login_attempts >= _LOGIN_ATTEMPT_LIMIT
            if locked:
                now = datetime.now(UTC)
                customer.locked_at = now
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
                        actor_type=AuditActorType.SYSTEM,
                        customer_id=customer.id,
                        action="customer.account_locked",
                        entity_type="customer",
                        entity_id=str(customer.id),
                        details={"failed_login_attempts": customer.failed_login_attempts},
                        ip_address=(ip_address or "")[:64] or None,
                    )
                )
            try:
                self._session.commit()
            except SQLAlchemyError as exc:
                self._session.rollback()
                raise ServiceError(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "Login attempt could not be recorded.",
                ) from exc
            raise ServiceError(
                status.HTTP_423_LOCKED if locked else status.HTTP_401_UNAUTHORIZED,
                "Account is locked." if locked else "Invalid username or PIN.",
            )
        if customer.account_status in {AccountStatus.SUSPENDED, AccountStatus.CLOSED}:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Account access is unavailable.")

        now = datetime.now(UTC)
        ttl_seconds = (
            self._settings.remembered_customer_session_ttl_seconds
            if request.remember_me
            else self._settings.customer_session_ttl_seconds
        )
        expires_at = now + timedelta(seconds=ttl_seconds)
        token = secrets.token_urlsafe(48)
        customer_session = CustomerSession(
            customer=customer,
            token_hash=_hash_session_token(token),
            expires_at=expires_at,
            last_seen_at=now,
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(user_agent or "")[:2000] or None,
        )
        customer.last_login_at = now
        customer.last_activity_at = now
        customer.failed_login_attempts = 0
        self._session.add(customer_session)
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Login could not be completed.",
            ) from exc

        login_attempt_limiter.clear(attempt_key)
        return CreatedCustomerSession(
            customer=customer,
            token=token,
            expires_at=expires_at,
            persistent=request.remember_me,
        )

    def authenticate(self, token: str | None) -> Customer:
        if not token:
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Login is required.")
        now = datetime.now(UTC)
        customer_session = self._session.scalar(
            select(CustomerSession)
            .options(joinedload(CustomerSession.customer))
            .where(
                CustomerSession.token_hash == _hash_session_token(token),
                CustomerSession.revoked_at.is_(None),
                CustomerSession.expires_at > now,
            )
            .limit(1)
        )
        if customer_session is None:
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Login is required.")
        customer = customer_session.customer
        if customer.locked_at is not None:
            raise ServiceError(status.HTTP_423_LOCKED, "Account is locked.")
        if customer.account_status in {AccountStatus.SUSPENDED, AccountStatus.CLOSED}:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Account access is unavailable.")
        customer_session.last_seen_at = now
        customer.last_activity_at = now
        self._session.commit()
        return customer

    def logout(self, token: str | None) -> None:
        if not token:
            return
        customer_session = self._session.scalar(
            select(CustomerSession)
            .where(CustomerSession.token_hash == _hash_session_token(token))
            .limit(1)
        )
        if customer_session is None or customer_session.revoked_at is not None:
            return
        customer_session.revoked_at = datetime.now(UTC)
        self._session.commit()


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(f"customer-session:{token}".encode()).hexdigest()
