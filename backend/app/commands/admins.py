from __future__ import annotations

import argparse
from datetime import UTC, datetime
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import Argon2PasswordHasher
from app.db.session import get_engine
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.schemas.admin_auth import AdminLoginRequest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or update an administrator account.")
    parser.add_argument("--username", required=True, help="The administrator login username.")
    return parser


def _read_credentials(username: str) -> AdminLoginRequest:
    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    try:
        return AdminLoginRequest(username=username, password=password)
    except ValidationError as exc:
        raise ValueError(
            "Use a 3-64 character lowercase username and a password of at least 8 characters."
        ) from exc


def save_admin(session: Session, credentials: AdminLoginRequest) -> AdminUser:
    """Create/update one admin; the legacy email column stores the login identifier."""
    admin = session.scalar(
        select(AdminUser).where(AdminUser.email == credentials.username).limit(1)
    )
    if admin is None:
        admin = AdminUser(
            email=credentials.username,
            password_hash="",
            role=AdminRole.ADMINISTRATOR,
        )
        session.add(admin)
    admin.password_hash = Argon2PasswordHasher().hash(
        credentials.password.get_secret_value()
    )
    admin.role = AdminRole.ADMINISTRATOR
    admin.is_active = True
    session.flush()
    session.execute(
        update(AdminSession)
        .where(AdminSession.admin_user_id == admin.id, AdminSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    session.commit()
    return admin


def main() -> None:
    arguments = _build_parser().parse_args()
    try:
        credentials = _read_credentials(arguments.username)
        with Session(get_engine(), expire_on_commit=False) as session:
            admin = save_admin(session, credentials)
        print(f"Administrator '{admin.email}' is ready.")
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
