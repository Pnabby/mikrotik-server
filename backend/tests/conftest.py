from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.admin_user import AdminUser
from app.models.customer import Customer
from app.models.enums import AdminRole
from app.models.router import Router


@pytest.fixture
def support_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def setup_connection(connection, _record):
        connection.create_function("char_length", 1, len)
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        now = datetime.now(UTC)
        source = Router(id="main", name="Flint Main", vpn_host="main.test")
        destination = Router(id="annex", name="Flint Annex", vpn_host="annex.test")
        session.add_all([source, destination])
        session.flush()
        customers = [
            Customer(
                router_id="main",
                username=username,
                email=f"{username}@example.com",
                pin_hash="hashed",
                mikrotik_user_verified_at=now,
                last_activity_at=now,
                terms_accepted_at=now,
                terms_version="1",
                privacy_notice_version="1",
            )
            for username in ("ama", "kwame")
        ]
        admin = AdminUser(
            email="admin@example.com", password_hash="hashed", role=AdminRole.ADMINISTRATOR
        )
        session.add_all([*customers, admin])
        session.commit()
        yield session, customers, admin, source, destination
    engine.dispose()
