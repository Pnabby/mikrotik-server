from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import HashingError, InvalidHashError, VerifyMismatchError

from app.core.config import Settings


class PinHashingError(RuntimeError):
    """Raised when secure PIN hashing cannot be completed."""


class PinHasher(Protocol):
    def hash(self, pin: str) -> str: ...

    def verify(self, pin_hash: str, pin: str) -> bool: ...


class Argon2PinHasher:
    """Argon2id PIN hashing with an application-side HMAC pepper."""

    def __init__(self, pepper: str, password_hasher: Argon2Hasher | None = None) -> None:
        if len(pepper) < 32:
            raise ValueError("PIN_HASH_SECRET must contain at least 32 characters.")
        self._pepper = pepper.encode("utf-8")
        self._password_hasher = password_hasher or Argon2Hasher()

    @classmethod
    def from_settings(cls, settings: Settings) -> Argon2PinHasher:
        if settings.pin_hash_secret is None:
            raise ValueError("PIN_HASH_SECRET must be configured.")
        return cls(settings.pin_hash_secret.get_secret_value())

    def hash(self, pin: str) -> str:
        try:
            return self._password_hasher.hash(self._peppered_pin(pin))
        except HashingError as exc:
            raise PinHashingError("PIN hashing failed.") from exc

    def verify(self, pin_hash: str, pin: str) -> bool:
        try:
            return self._password_hasher.verify(pin_hash, self._peppered_pin(pin))
        except (InvalidHashError, VerifyMismatchError):
            return False

    def _peppered_pin(self, pin: str) -> bytes:
        return hmac.new(self._pepper, pin.encode("utf-8"), hashlib.sha256).digest()


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class Argon2PasswordHasher:
    """Argon2id hashing for administrator passwords."""

    def __init__(self, password_hasher: Argon2Hasher | None = None) -> None:
        self._password_hasher = password_hasher or Argon2Hasher()

    def hash(self, password: str) -> str:
        try:
            return self._password_hasher.hash(password)
        except HashingError as exc:
            raise PinHashingError("Password hashing failed.") from exc

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._password_hasher.verify(password_hash, password)
        except (InvalidHashError, VerifyMismatchError):
            return False
