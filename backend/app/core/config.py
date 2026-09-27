from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class RouterSettings(BaseModel):
    """Legacy environment router metadata accepted only by the one-time importer."""

    router_id: str
    name: str
    host: str
    port: int = 8728
    hotspot_network: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    api_cors_origins: str = "http://localhost:5173,http://localhost:5174"
    frontend_url: str = "http://localhost:5173"
    frontend_dist_dir: Path = PROJECT_ROOT / "public" / "dist"
    admin_frontend_url: str = "http://localhost:5174"
    admin_dist_dir: Path = PROJECT_ROOT / "admin" / "dist"

    database_url: str | None = None

    brevo_api_key: SecretStr | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "Vlad WiFi"
    brevo_api_url: str = "https://api.brevo.com/v3"
    brevo_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    mnotify_api_key: SecretStr | None = None
    mnotify_sender_id: str | None = None
    mnotify_api_url: str = "https://api.mnotify.com/api/sms/quick"
    mnotify_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    otp_hash_secret: SecretStr | None = None
    otp_code_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    otp_resend_cooldown_seconds: int = Field(default=60, ge=1, le=3600)
    otp_max_attempts: int = Field(default=5, ge=1, le=20)
    otp_max_requests_per_hour: int = Field(default=5, ge=1, le=100)
    pin_hash_secret: SecretStr | None = None
    customer_session_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 7,
        ge=60 * 60,
        le=60 * 60 * 24 * 30,
    )
    remembered_customer_session_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 30,
        ge=60 * 60 * 24,
        le=60 * 60 * 24 * 90,
    )
    inactive_account_retention_days: int = Field(default=365, ge=30, le=3650)
    inactive_account_cleanup_enabled: bool = False
    inactive_account_cleanup_interval_seconds: int = Field(
        default=60 * 60 * 24,
        ge=60 * 5,
        le=60 * 60 * 24 * 7,
    )
    admin_session_ttl_seconds: int = Field(
        default=60 * 60 * 12,
        ge=15 * 60,
        le=60 * 60 * 24 * 7,
    )

    mikrotik_username: str | None = None
    mikrotik_password: SecretStr | None = None
    mikrotik_plaintext_login: bool = True
    mikrotik_use_ssl: bool = False
    mikrotik_ssl_verify: bool = True
    mikrotik_ssl_verify_hostname: bool = True
    mikrotik_router_id: str = "flint-main"
    mikrotik_registration_profile: str = "disabled"
    router_metrics_collection_enabled: bool = True
    router_metrics_sample_interval_seconds: int = Field(default=300, ge=60, le=3600)
    router_metrics_interface: str = "ether1"
    # Retained temporarily so existing JSON configuration can be imported into PostgreSQL.
    # Runtime router resolution never reads this value.
    mikrotik_routers_json: list[RouterSettings] = Field(default_factory=list)

    paystack_secret_key: SecretStr | None = None
    paystack_public_key: str | None = None
    paystack_callback_url: str | None = None
    paystack_api_url: str = "https://api.paystack.co"
    paystack_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    paystack_webhook_secret: SecretStr | None = None

    @property
    def cors_origins(self) -> list[str]:
        origins = [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]
        return origins or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
