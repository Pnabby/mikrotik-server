from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.router import Router

DEFAULT_ROUTER_ID = "flint-main"


@dataclass(frozen=True, slots=True)
class RouterDefinition:
    """Validated connection metadata read from the database router catalogue."""

    router_id: str
    name: str
    host: str
    port: int
    hotspot_network: str


class UnknownRouterError(ValueError):
    """Raised when an active, fully configured router cannot be resolved."""


def get_router(session: Session, router_id: str) -> RouterDefinition:
    """Resolve an active router by its exact database ID."""

    normalized_router_id = router_id.strip()
    router = session.get(Router, normalized_router_id) if normalized_router_id else None
    if router is None or not router.is_active:
        raise UnknownRouterError("Router is not configured.")
    return _router_definition(router)


def iter_routers(session: Session) -> Sequence[RouterDefinition]:
    """Return active, fully configured routers in their database display order."""

    routers = session.scalars(
        select(Router)
        .where(
            Router.is_active.is_(True),
            Router.hotspot_network.is_not(None),
        )
        .order_by(Router.display_order, Router.name, Router.id)
    ).all()
    return tuple(_router_definition(router) for router in routers)


def _router_definition(router: Router) -> RouterDefinition:
    hotspot_network = (router.hotspot_network or "").strip()
    if not hotspot_network:
        raise UnknownRouterError("Router is not fully configured.")
    return RouterDefinition(
        router_id=router.id,
        name=router.name,
        host=router.vpn_host,
        port=router.api_port,
        hotspot_network=hotspot_network,
    )
