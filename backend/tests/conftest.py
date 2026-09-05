from __future__ import annotations

import json
import os
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.router import Router

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


@pytest.fixture
def router_catalog_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def add_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(engine, tables=[Router.__table__])
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                Router(
                    id=item["router_id"],
                    name=item["name"],
                    vpn_host=item["host"],
                    api_port=item["port"],
                    hotspot_network=item["hotspot_network"],
                    display_order=index,
                )
                for index, item in enumerate(TEST_ROUTERS)
            ]
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine, tables=[Router.__table__])
    engine.dispose()


@pytest.fixture(autouse=True)
def configure_app_router_catalog(router_catalog_session: Session) -> Generator[None, None, None]:
    def override_session() -> Generator[Session, None, None]:
        yield router_catalog_session

    app.dependency_overrides[get_db_session] = override_session
    yield
    if app.dependency_overrides.get(get_db_session) is override_session:
        app.dependency_overrides.pop(get_db_session)
