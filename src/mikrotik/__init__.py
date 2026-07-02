"""Utilities for connecting to a MikroTik router."""

from mikrotik.client import MikroTikClient, MikroTikConfig

__all__ = ["MikroTikClient", "MikroTikConfig", "app"]


def __getattr__(name: str):
    if name == "app":
        from mikrotik.api import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
