from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.security import PasswordHasher, PinHashingError
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.schemas.admin_auth import AdminLoginRequest

ADMIN_SESSION_COOKIE = "flint_admin_session"
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60


class AdminLoginAttemptLimiter:
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
                raise ServiceError(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts.")

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


admin_login_attempt_limiter = AdminLoginAttemptLimiter()


@dataclass(frozen=True, slots=True)
class CreatedAdminSession:
    admin: AdminUser
    token: str
    expires_at: datetime


class AdminAuthenticationService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def login(
        self,
        request: AdminLoginRequest,
        password_hasher: PasswordHasher,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> CreatedAdminSession:
        attempt_key = f"{ip_address or 'unknown'}:{request.username}"
        admin_login_attempt_limiter.enforce(attempt_key)
        admin = self._session.scalar(
            select(AdminUser).where(AdminUser.email == request.username).limit(1)
        )
        password = request.password.get_secret_value()
        if admin is None:
            try:
                password_hasher.hash(password)
            except PinHashingError:
                pass
            admin_login_attempt_limiter.record_failure(attempt_key)
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Invalid admin credentials.")
        if not password_hasher.verify(admin.password_hash, password):
            admin_login_attempt_limiter.record_failure(attempt_key)
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Invalid admin credentials.")
        if not admin.is_active:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Admin access is unavailable.")

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._settings.admin_session_ttl_seconds)
        token = secrets.token_urlsafe(48)
        stored_session = AdminSession(
            admin_user=admin,
            token_hash=_hash_session_token(token),
            expires_at=expires_at,
            last_seen_at=now,
            ip_address=(ip_address or "")[:64] or None,
            user_agent=(user_agent or "")[:2000] or None,
        )
        admin.last_login_at = now
        self._session.add(stored_session)
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Admin login could not be completed.",
            ) from exc

        admin_login_attempt_limiter.clear(attempt_key)
        return CreatedAdminSession(admin=admin, token=token, expires_at=expires_at)

    def authenticate(self, token: str | None) -> AdminUser:
        if not token:
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Admin login is required.")
        now = datetime.now(UTC)
        stored_session = self._session.scalar(
            select(AdminSession)
            .options(joinedload(AdminSession.admin_user))
            .where(
                AdminSession.token_hash == _hash_session_token(token),
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > now,
            )
            .limit(1)
        )
        if stored_session is None:
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "Admin login is required.")
        admin = stored_session.admin_user
        if not admin.is_active:
            raise ServiceError(status.HTTP_403_FORBIDDEN, "Admin access is unavailable.")
        stored_session.last_seen_at = now
        self._session.commit()
        return admin

    def logout(self, token: str | None) -> None:
        if not token:
            return
        stored_session = self._session.scalar(
            select(AdminSession)
            .where(AdminSession.token_hash == _hash_session_token(token))
            .limit(1)
        )
        if stored_session is None or stored_session.revoked_at is not None:
            return
        stored_session.revoked_at = datetime.now(UTC)
        self._session.commit()


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(f"admin-session:{token}".encode()).hexdigest()
