import pytest
from sqlalchemy.orm import Session

from app.integrations.mikrotik.client import MikroTikConfig
from app.integrations.mikrotik.registry import UnknownRouterError, get_router, iter_routers
from app.models.router import Router


def test_router_registry_reads_all_sites_from_database(
    router_catalog_session: Session,
) -> None:
    routers = iter_routers(router_catalog_session)

    assert [router.router_id for router in routers] == [
        "flint-main",
        "platinum",
        "flint-annex",
    ]
    assert get_router(router_catalog_session, "flint-main").host == "192.0.2.2"
    assert get_router(router_catalog_session, "flint-main").port == 8728
    assert (
        get_router(router_catalog_session, "flint-main").hotspot_network
        == "198.51.100.0/26"
    )
    assert get_router(router_catalog_session, "platinum").host == "192.0.2.3"
    assert get_router(router_catalog_session, "flint-annex").host == "192.0.2.4"


def test_router_registry_requires_an_exact_active_database_id(
    router_catalog_session: Session,
) -> None:
    with pytest.raises(UnknownRouterError, match="not configured"):
        get_router(router_catalog_session, "192.0.2.3")

    with pytest.raises(UnknownRouterError, match="not configured"):
        get_router(router_catalog_session, "Platinum")

    router_catalog_session.get(Router, "platinum").is_active = False  # type: ignore[union-attr]
    router_catalog_session.commit()
    with pytest.raises(UnknownRouterError, match="not configured"):
        get_router(router_catalog_session, "platinum")


def test_client_config_uses_database_host_and_shared_environment_credentials(
    router_catalog_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIKROTIK_USERNAME", "api-user")
    monkeypatch.setenv("MIKROTIK_PASSWORD", "api-password")
    monkeypatch.setenv("MIKROTIK_HOST", "203.0.113.10")
    monkeypatch.setenv("MIKROTIK_PORT", "9999")

    flint_main_config = MikroTikConfig.from_env(
        get_router(router_catalog_session, "flint-main")
    )
    platinum_config = MikroTikConfig.from_env(
        get_router(router_catalog_session, "platinum")
    )

    assert flint_main_config.host == "192.0.2.2"
    assert platinum_config.host == "192.0.2.3"
    assert flint_main_config.port == platinum_config.port == 8728
    assert flint_main_config.username == platinum_config.username == "api-user"
    assert flint_main_config.password == platinum_config.password == "api-password"
    assert "api-user" not in repr(flint_main_config)
    assert "api-password" not in repr(flint_main_config)
