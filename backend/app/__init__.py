"""Vlad WiFi backend package."""

from app.integrations.mikrotik import MikroTikClient, MikroTikConfig

__all__ = ["MikroTikClient", "MikroTikConfig", "app"]


def __getattr__(name: str):
    if name == "app":
        from app.main import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
