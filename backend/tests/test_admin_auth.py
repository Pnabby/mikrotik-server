from __future__ import annotations

import hashlib
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import Argon2PasswordHasher
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.services.admin_auth import ADMIN_SESSION_COOKIE, admin_login_attempt_limiter

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "TestAdminPassword9!"


@pytest.fixture
def admin_auth_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[AdminUser.__table__, AdminSession.__table__])
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            AdminUser(
                email=ADMIN_USERNAME,
                password_hash=Argon2PasswordHasher().hash(ADMIN_PASSWORD),
                role=AdminRole.ADMINISTRATOR,
            )
        )
        session.commit()
        yield session
    Base.metadata.drop_all(engine, tables=[AdminSession.__table__, AdminUser.__table__])
    engine.dispose()


@pytest.fixture
def admin_client(admin_auth_session: Session) -> Generator[TestClient, None, None]:
    previous_override = app.dependency_overrides.get(get_db_session)

    def override_session() -> Generator[Session, None, None]:
        yield admin_auth_session

    app.dependency_overrides[get_db_session] = override_session
    admin_login_attempt_limiter.clear(f"testclient:{ADMIN_USERNAME}")
    with TestClient(app) as client:
        yield client
    if previous_override is None:
        app.dependency_overrides.pop(get_db_session, None)
    else:
        app.dependency_overrides[get_db_session] = previous_override


def test_admin_login_creates_a_hashed_http_only_session(
    admin_client: TestClient,
    admin_auth_session: Session,
) -> None:
    response = admin_client.post(
        "/api/admin/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json() == {
        "username": ADMIN_USERNAME,
        "role": "administrator",
        "redirect_to": "/",
    }
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    raw_token = admin_client.cookies.get(ADMIN_SESSION_COOKIE)
    stored_session = admin_auth_session.scalar(select(AdminSession))
    assert raw_token is not None
    assert stored_session is not None
    assert raw_token not in stored_session.token_hash
    expected_hash = hashlib.sha256(f"admin-session:{raw_token}".encode()).hexdigest()
    assert stored_session.token_hash == expected_hash


def test_admin_session_can_be_restored_and_logged_out(admin_client: TestClient) -> None:
    login_response = admin_client.post(
        "/api/admin/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert login_response.status_code == 200

    session_response = admin_client.get("/api/admin/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["username"] == ADMIN_USERNAME

    logout_response = admin_client.post("/api/admin/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json() == {"logged_out": True}
    assert admin_client.get("/api/admin/auth/session").status_code == 401


def test_admin_login_rejects_an_incorrect_password(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/admin/auth/login",
        json={"username": ADMIN_USERNAME, "password": "NotThePassword"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}
    assert ADMIN_PASSWORD not in response.text


def test_inactive_admin_cannot_log_in(
    admin_client: TestClient,
    admin_auth_session: Session,
) -> None:
    admin = admin_auth_session.scalar(select(AdminUser))
    assert admin is not None
    admin.is_active = False
    admin_auth_session.commit()

    response = admin_client.post(
        "/api/admin/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}
