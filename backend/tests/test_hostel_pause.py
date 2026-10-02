from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.integrations.mikrotik.registry import UnknownRouterError, get_router, iter_routers
from app.models.router import Router
from app.services.admin_dashboard import AdminDashboardService
from app.services.router_catalog import RouterCatalogEntry, upsert_router


def test_disabled_hostel_stays_paused_after_catalog_import_and_resumes():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def add_char_length(connection, _record):
        connection.create_function("char_length", 1, len)

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        router = Router(id="hall", name="Hall", vpn_host="hall.example",
                        hotspot_network="10.0.0.0/24", is_active=False)
        session.add(router)
        session.commit()
        upsert_router(session, RouterCatalogEntry(
            router_id="hall", name="Hall", host="hall.example", port=8728,
            hotspot_network="10.0.0.0/24"))
        session.commit()
        assert not router.is_active
        assert not iter_routers(session)
        with pytest.raises(UnknownRouterError):
            get_router(session, "hall")
        service = AdminDashboardService(session)
        assert not service.access_points(router).router_reachable
        assert not service._routers(None)
        assert not service._routers("hall")
        assert not service._revenue_forecasts([], datetime.now(UTC))
        router.is_active = True
        session.commit()
        assert get_router(session, "hall").router_id == "hall"
        assert len(iter_routers(session)) == 1
        assert service._routers("hall") == [router]

