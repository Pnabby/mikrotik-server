from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class RouterSettings(BaseModel):
    """Environment-provided connection and display metadata for one router."""

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

    database_url: str | None = None

    mikrotik_username: str | None = None
    mikrotik_password: SecretStr | None = None
    mikrotik_plaintext_login: bool = True
    mikrotik_use_ssl: bool = False
    mikrotik_ssl_verify: bool = True
    mikrotik_ssl_verify_hostname: bool = True
    mikrotik_router_id: str = "flint-main"
    mikrotik_routers_json: list[RouterSettings] = Field(default_factory=list)

    paystack_secret_key: SecretStr | None = None
    paystack_public_key: str | None = None
    paystack_webhook_secret: SecretStr | None = None

    @property
    def cors_origins(self) -> list[str]:
        origins = [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]
        return origins or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
