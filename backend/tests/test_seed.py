from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.commands.seed import SeedDocument, export_seed_document, import_seed_document
from app.core.security import Argon2PasswordHasher
from app.db.base import Base
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.models.router import Router


def _engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def add_sqlite_functions(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.create_function("char_length", 1, len)  # type: ignore[attr-defined]

    Base.metadata.create_all(
        engine,
        tables=[Router.__table__, AdminUser.__table__, AdminSession.__table__],
    )
    return engine


def test_seed_document_round_trip_is_idempotent_and_preserves_admin_login() -> None:
    source_engine = _engine()
    target_engine = _engine()
    password_hash = Argon2PasswordHasher().hash("ExistingAdmin9!")
    with Session(source_engine) as source:
        source.add(
            Router(
                id="platinum",
                name="Platinum",
                location="North campus",
                vpn_host="192.0.2.3",
                api_port=8728,
                hotspot_network="198.51.100.64/26",
                display_order=1,
            )
        )
        source.add(
            AdminUser(
                email="admin",
                password_hash=password_hash,
                role=AdminRole.ADMINISTRATOR,
            )
        )
        source.commit()
        serialized = export_seed_document(source).model_dump_json()

    document = SeedDocument.model_validate_json(serialized)
    with Session(target_engine, expire_on_commit=False) as target:
        assert import_seed_document(target, document) == (1, 1)
        assert import_seed_document(target, document) == (1, 1)
        assert len(target.scalars(select(Router)).all()) == 1
        assert len(target.scalars(select(AdminUser)).all()) == 1
        admin = target.scalar(select(AdminUser))
        assert admin is not None
        assert admin.password_hash == password_hash
        assert Argon2PasswordHasher().verify(admin.password_hash, "ExistingAdmin9!")

    source_engine.dispose()
    target_engine.dispose()


def test_changed_seed_password_revokes_existing_admin_sessions() -> None:
    engine = _engine()
    original_hash = Argon2PasswordHasher().hash("OriginalAdmin9!")
    replacement_hash = Argon2PasswordHasher().hash("ReplacementAdmin9!")
    with Session(engine, expire_on_commit=False) as session:
        admin = AdminUser(
            email="admin",
            password_hash=original_hash,
            role=AdminRole.ADMINISTRATOR,
        )
        session.add(admin)
        session.flush()
        admin_session = AdminSession(
            admin_user_id=admin.id,
            token_hash="seed-test-session",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(admin_session)
        session.commit()

        document = SeedDocument(
            exported_at=datetime.now(UTC),
            hostels=[],
            admins=[
                {
                    "username": "admin",
                    "password_hash": replacement_hash,
                    "role": "administrator",
                    "is_active": True,
                }
            ],
        )
        import_seed_document(session, document)
        session.refresh(admin_session)

        assert admin.password_hash == replacement_hash
        assert admin_session.revoked_at is not None

    engine.dispose()
