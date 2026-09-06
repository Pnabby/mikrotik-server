from app.core.config import Settings
from app.core.security import Argon2PasswordHasher, Argon2PinHasher


def test_pin_hasher_uses_argon2id_and_a_secret_pepper() -> None:
    settings = Settings(
        _env_file=None,
        pin_hash_secret="a-secure-pin-pepper-that-is-over-32-characters",
    )
    hasher = Argon2PinHasher.from_settings(settings)

    pin_hash = hasher.hash("483265")

    assert pin_hash.startswith("$argon2id$")
    assert "483265" not in pin_hash
    assert hasher.verify(pin_hash, "483265") is True
    assert hasher.verify(pin_hash, "111111") is False


def test_admin_password_hasher_uses_argon2id() -> None:
    hasher = Argon2PasswordHasher()

    password_hash = hasher.hash("StrongAdminPassword9!")

    assert password_hash.startswith("$argon2id$")
    assert "StrongAdminPassword9!" not in password_hash
    assert hasher.verify(password_hash, "StrongAdminPassword9!") is True
    assert hasher.verify(password_hash, "wrong-password") is False
