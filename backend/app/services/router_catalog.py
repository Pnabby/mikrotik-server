from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import RouterSettings
from app.models.router import Router

ROUTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class RouterCatalogError(ValueError):
    """Raised when router catalogue data is invalid or conflicts with existing data."""


@dataclass(frozen=True, slots=True)
class RouterCatalogEntry:
    router_id: str
    name: str
    host: str
    port: int
    hotspot_network: str
    display_order: int = 0
    location: str | None = None

    @classmethod
    def from_legacy_settings(
        cls,
        settings: RouterSettings,
        *,
        display_order: int,
    ) -> RouterCatalogEntry:
        return cls(
            router_id=settings.router_id,
            name=settings.name,
            host=settings.host,
            port=settings.port,
            hotspot_network=settings.hotspot_network,
            display_order=display_order,
        ).validated()

    def validated(self) -> RouterCatalogEntry:
        router_id = self.router_id.strip().lower()
        name = self.name.strip()
        host = self.host.strip()
        hotspot_network = self.hotspot_network.strip()
        location = self.location.strip() if self.location else None
        if not ROUTER_ID_PATTERN.fullmatch(router_id):
            raise RouterCatalogError(
                "Router IDs must contain only lowercase letters, numbers, and hyphens."
            )
        if not name or not host or not hotspot_network:
            raise RouterCatalogError("Router name, host, and hotspot network are required.")
        if not 1 <= self.port <= 65535:
            raise RouterCatalogError("Router API port must be between 1 and 65535.")
        if self.display_order < 0:
            raise RouterCatalogError("Router display order cannot be negative.")
        return RouterCatalogEntry(
            router_id=router_id,
            name=name,
            host=host,
            port=self.port,
            hotspot_network=hotspot_network,
            display_order=self.display_order,
            location=location,
        )


def upsert_router(session: Session, entry: RouterCatalogEntry) -> Router:
    validated = entry.validated()
    router = session.get(Router, validated.router_id)
    if router is None:
        router = Router(id=validated.router_id)
        session.add(router)
    router.name = validated.name
    router.vpn_host = validated.host
    router.api_port = validated.port
    router.hotspot_network = validated.hotspot_network
    router.display_order = validated.display_order
    router.location = validated.location
    router.is_active = True
    return router


def import_legacy_routers(
    session: Session,
    configured_routers: list[RouterSettings],
) -> tuple[str, ...]:
    imported_ids: list[str] = []
    try:
        for display_order, configured_router in enumerate(configured_routers):
            entry = RouterCatalogEntry.from_legacy_settings(
                configured_router,
                display_order=display_order,
            )
            upsert_router(session, entry)
            imported_ids.append(entry.router_id.strip().lower())
        session.commit()
    except (IntegrityError, RouterCatalogError) as exc:
        session.rollback()
        if isinstance(exc, RouterCatalogError):
            raise
        raise RouterCatalogError(
            "Router IDs and hosts must be unique in the database catalogue."
        ) from exc
    return tuple(imported_ids)
