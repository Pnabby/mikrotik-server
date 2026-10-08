"""Authenticated recovery snapshots; credentials never enter journal JSON or logs."""

import base64
import json
import uuid

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings


class TransferSnapshotCipher:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise ValueError("PIN_HASH_SECRET must contain at least 32 characters.")
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"vlad-wifi/hostel-transfer/snapshot/v1",
        ).derive(secret.encode())
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    @classmethod
    def from_settings(cls, settings: Settings):
        if settings.pin_hash_secret is None:
            raise ValueError("PIN_HASH_SECRET is required for transfer recovery.")
        return cls(settings.pin_hash_secret.get_secret_value())

    def encrypt(self, operation_id: uuid.UUID, snapshot: dict) -> str:
        envelope = {"operation_id": str(operation_id), "snapshot": snapshot}
        return self._fernet.encrypt(json.dumps(envelope).encode()).decode()

    def decrypt(self, operation_id: uuid.UUID, token: str) -> dict:
        if not isinstance(token, str):
            raise InvalidToken("Recovery snapshot is missing.")
        envelope = json.loads(self._fernet.decrypt(token))
        if not isinstance(envelope, dict) or not isinstance(envelope.get("snapshot"), dict):
            raise InvalidToken("Recovery snapshot is malformed.")
        if envelope.get("operation_id") != str(operation_id):
            raise InvalidToken("Recovery snapshot belongs to another operation.")
        return envelope["snapshot"]
