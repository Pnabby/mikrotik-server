from __future__ import annotations

import json
import os

import pytest

from app.core.config import get_settings


TEST_ROUTERS = [
    {
        "router_id": "flint-main",
        "name": "Flint Main",
        "host": "192.0.2.2",
        "port": 8728,
        "hotspot_network": "198.51.100.0/26",
    },
    {
        "router_id": "platinum",
        "name": "Platinum",
        "host": "192.0.2.3",
        "port": 8728,
        "hotspot_network": "198.51.100.64/26",
    },
    {
        "router_id": "flint-annex",
        "name": "Flint Annex",
        "host": "192.0.2.4",
        "port": 8728,
        "hotspot_network": "198.51.100.128/26",
    },
]

os.environ["MIKROTIK_ROUTERS_JSON"] = json.dumps(TEST_ROUTERS)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
