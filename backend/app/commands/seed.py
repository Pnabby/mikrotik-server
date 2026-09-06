from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.models.router import Router
from app.schemas.admin_auth import ADMIN_USERNAME_PATTERN, normalize_admin_username
from app.services.router_catalog import ROUTER_ID_PATTERN


class SeedHostel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    router_id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    location: str | None = Field(default=None, max_length=255)
    vpn_host: str = Field(min_length=1, max_length=255)
    api_port: int = Field(gt=0, le=65535)
    hotspot_network: str | None = Field(default=None, max_length=255)
    display_order: int = Field(ge=0)
    is_active: bool = True

    @field_validator("router_id")
    @classmethod
    def validate_router_id(cls, value: str) -> str:
        normalized = value.lower()
        if not ROUTER_ID_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid hostel ID in seed data.")
        return normalized


class SeedAdmin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=64)
    password_hash: str = Field(min_length=20, max_length=255)
    role: AdminRole
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = normalize_admin_username(value)
        if not ADMIN_USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid administrator username in seed data.")
        return normalized

    @field_validator("password_hash")
    @classmethod
    def validate_password_hash(cls, value: str) -> str:
        if not value.startswith("$argon2"):
            raise ValueError("Seed administrator passwords must be Argon2 hashes.")
        return value


class SeedDocument(BaseModel):
    version: Literal[1] = 1
    exported_at: datetime
    hostels: list[SeedHostel]
    admins: list[SeedAdmin]


def export_seed_document(session: Session) -> SeedDocument:
    hostels = session.scalars(
        select(Router).order_by(Router.display_order, Router.name, Router.id)
    ).all()
    admins = session.scalars(select(AdminUser).order_by(AdminUser.email)).all()
    return SeedDocument(
        exported_at=datetime.now(UTC),
        hostels=[
            SeedHostel(
                router_id=hostel.id,
                name=hostel.name,
                location=hostel.location,
                vpn_host=hostel.vpn_host,
                api_port=hostel.api_port,
                hotspot_network=hostel.hotspot_network,
                display_order=hostel.display_order,
                is_active=hostel.is_active,
            )
            for hostel in hostels
        ],
        admins=[
            SeedAdmin(
                username=admin.email,
                password_hash=admin.password_hash,
                role=admin.role,
                is_active=admin.is_active,
            )
            for admin in admins
        ],
    )


def import_seed_document(session: Session, document: SeedDocument) -> tuple[int, int]:
    for seed_hostel in document.hostels:
        hostel = session.get(Router, seed_hostel.router_id)
        if hostel is None:
            hostel = Router(id=seed_hostel.router_id)
            session.add(hostel)
        hostel.name = seed_hostel.name
        hostel.location = seed_hostel.location
        hostel.vpn_host = seed_hostel.vpn_host
        hostel.api_port = seed_hostel.api_port
        hostel.hotspot_network = seed_hostel.hotspot_network
        hostel.display_order = seed_hostel.display_order
        hostel.is_active = seed_hostel.is_active

    for seed_admin in document.admins:
        admin = session.scalar(
            select(AdminUser).where(AdminUser.email == seed_admin.username).limit(1)
        )
        if admin is None:
            admin = AdminUser(email=seed_admin.username, password_hash=seed_admin.password_hash)
            session.add(admin)
        password_changed = admin.password_hash != seed_admin.password_hash
        admin.password_hash = seed_admin.password_hash
        admin.role = seed_admin.role
        admin.is_active = seed_admin.is_active
        if password_changed and admin.id is not None:
            session.execute(
                update(AdminSession)
                .where(
                    AdminSession.admin_user_id == admin.id,
                    AdminSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(UTC))
            )

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    return len(document.hostels), len(document.admins)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export or import hostel and administrator seed data."
    )
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--export", type=Path, metavar="FILE", dest="export_path")
    operation.add_argument("--import", type=Path, metavar="FILE", dest="import_path")
    return parser


def _write_document(path: Path, document: SeedDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def _read_document(path: Path) -> SeedDocument:
    return SeedDocument.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    arguments = _build_parser().parse_args()
    try:
        with Session(get_engine(), expire_on_commit=False) as session:
            if arguments.export_path:
                document = export_seed_document(session)
                _write_document(arguments.export_path, document)
                print(
                    f"Exported {len(document.hostels)} hostel(s) and "
                    f"{len(document.admins)} administrator(s) to {arguments.export_path}."
                )
                print("Keep this file private: it contains administrator password hashes.")
                return
            document = _read_document(arguments.import_path)
            hostel_count, admin_count = import_seed_document(session, document)
        print(f"Seeded {hostel_count} hostel(s) and {admin_count} administrator(s).")
    except (OSError, ValidationError, SQLAlchemyError) as exc:
        raise SystemExit(f"Seed operation failed: {type(exc).__name__}.") from exc


if __name__ == "__main__":
    main()
