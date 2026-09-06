from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models.router import Router
from app.services.router_catalog import (
    RouterCatalogEntry,
    RouterCatalogError,
    import_legacy_routers,
    upsert_router,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the database router catalogue.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List routers currently stored in the database.")
    commands.add_parser(
        "import-env",
        help="Import the legacy MIKROTIK_ROUTERS_JSON value into the database.",
    )
    add = commands.add_parser("add", help="Add or update one database router.")
    add.add_argument("--id", required=True, dest="router_id")
    add.add_argument("--name", required=True)
    add.add_argument("--host", required=True)
    add.add_argument("--port", type=int, default=8728)
    add.add_argument("--network", required=True, dest="hotspot_network")
    add.add_argument("--location")
    add.add_argument("--order", type=int, default=0, dest="display_order")
    return parser


def _list_routers(session: Session) -> None:
    routers = session.scalars(
        select(Router).order_by(Router.display_order, Router.name, Router.id)
    ).all()
    if not routers:
        print("No routers are stored in the database.")
        return
    for router in routers:
        state = "active" if router.is_active else "inactive"
        network = router.hotspot_network or "not configured"
        print(f"{router.id}: {router.name} [{state}] port={router.api_port} network={network}")


def _import_environment_routers(session: Session) -> None:
    configured_routers = get_settings().mikrotik_routers_json
    if not configured_routers:
        raise RouterCatalogError("MIKROTIK_ROUTERS_JSON does not contain any routers to import.")
    imported_ids = import_legacy_routers(session, configured_routers)
    print(f"Imported {len(imported_ids)} router(s): {', '.join(imported_ids)}")


def _add_router(session: Session, arguments: argparse.Namespace) -> None:
    entry = RouterCatalogEntry(
        router_id=arguments.router_id,
        name=arguments.name,
        host=arguments.host,
        port=arguments.port,
        hotspot_network=arguments.hotspot_network,
        display_order=arguments.display_order,
        location=arguments.location,
    )
    try:
        router = upsert_router(session, entry)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise RouterCatalogError("Another router already uses that host.") from exc
    print(f"Saved router {router.id} in the database catalogue.")


def main() -> None:
    arguments = _build_parser().parse_args()
    try:
        with Session(get_engine()) as session:
            if arguments.command == "list":
                _list_routers(session)
            elif arguments.command == "import-env":
                _import_environment_routers(session)
            elif arguments.command == "add":
                _add_router(session, arguments)
    except (RouterCatalogError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
