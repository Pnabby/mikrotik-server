from sqlalchemy.orm import Session

from app.core.config import RouterSettings
from app.integrations.mikrotik.registry import get_router, iter_routers
from app.models.router import Router
from app.services.router_catalog import RouterCatalogEntry, import_legacy_routers, upsert_router


def test_import_legacy_routers_upserts_complete_database_records(
    router_catalog_session: Session,
) -> None:
    imported = import_legacy_routers(
        router_catalog_session,
        [
            RouterSettings(
                router_id="new-hostel",
                name="New Hostel",
                host="192.0.2.20",
                port=8729,
                hotspot_network="198.51.100.192/26",
            )
        ],
    )

    assert imported == ("new-hostel",)
    router = router_catalog_session.get(Router, "new-hostel")
    assert router is not None
    assert router.vpn_host == "192.0.2.20"
    assert router.api_port == 8729
    assert router.hotspot_network == "198.51.100.192/26"
    assert get_router(router_catalog_session, "new-hostel").name == "New Hostel"


def test_database_router_order_and_active_state_control_public_catalogue(
    router_catalog_session: Session,
) -> None:
    router = router_catalog_session.get(Router, "flint-annex")
    assert router is not None
    router.is_active = False
    upsert_router(
        router_catalog_session,
        RouterCatalogEntry(
            router_id="priority-hostel",
            name="Priority Hostel",
            host="192.0.2.30",
            port=8728,
            hotspot_network="203.0.113.0/26",
            display_order=0,
        ),
    )
    router_catalog_session.commit()

    router_ids = [item.router_id for item in iter_routers(router_catalog_session)]

    assert "flint-annex" not in router_ids
    assert router_ids[:2] == ["flint-main", "priority-hostel"]
