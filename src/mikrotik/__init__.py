"""Utilities for connecting to a MikroTik router."""

from mikrotik.client import MikroTikClient, MikroTikConfig
from mikrotik.routers import ROUTERS, RouterDefinition

__all__ = ["MikroTikClient", "MikroTikConfig", "ROUTERS", "RouterDefinition", "app"]


def __getattr__(name: str):
    if name == "app":
        from mikrotik.api import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
