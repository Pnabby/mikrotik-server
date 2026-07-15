import pytest

from mikrotik.client import MikroTikConfig
from mikrotik.routers import ROUTERS, UnknownRouterError, get_router


def test_router_registry_contains_all_wireguard_sites() -> None:
    assert list(ROUTERS) == ["flint-main", "platinum", "flint-annex"]
    assert get_router("flint-main").host == "10.20.20.2"
    assert get_router("flint-main").port == 8728
    assert get_router("flint-main").hotspot_network == "192.168.88.0/23"
    assert get_router("platinum").host == "10.20.20.3"
    assert get_router("platinum").port == 8728
    assert get_router("platinum").hotspot_network == "192.168.92.0/23"
    assert get_router("flint-annex").host == "10.20.20.4"
    assert get_router("flint-annex").port == 8728
    assert get_router("flint-annex").hotspot_network == "192.168.90.0/23"


def test_router_registry_requires_an_exact_server_side_id() -> None:
    with pytest.raises(UnknownRouterError, match="not configured"):
        get_router("10.20.20.3")

    with pytest.raises(UnknownRouterError, match="not configured"):
        get_router("Platinum")


def test_client_config_uses_registry_host_and_shared_environment_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIKROTIK_USERNAME", "api-user")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "api-password")
    monkeypatch.setenv("MIKROTIK_HOST", "203.0.113.10")
    monkeypatch.setenv("MIKROTIK_PORT", "9999")

    flint_main_config = MikroTikConfig.from_env(get_router("flint-main"))
    platinum_config = MikroTikConfig.from_env(get_router("platinum"))

    assert flint_main_config.host == "10.20.20.2"
    assert platinum_config.host == "10.20.20.3"
    assert flint_main_config.port == platinum_config.port == 8728
    assert flint_main_config.username == platinum_config.username == "api-user"
    assert flint_main_config.password == platinum_config.password == "api-password"
    assert "api-user" not in repr(flint_main_config)
    assert "api-password" not in repr(flint_main_config)
