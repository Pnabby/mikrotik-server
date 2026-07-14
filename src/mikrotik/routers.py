from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class RouterDefinition:
    """Non-secret connection metadata for one allowed MikroTik router."""

    router_id: str
    name: str
    host: str
    port: int
    hotspot_network: str


class UnknownRouterError(ValueError):
    """Raised when a router ID is not present in the server-side registry."""


_ROUTER_DEFINITIONS = (
    RouterDefinition(
        router_id="flint-main",
        name="Flint Main",
        host="10.20.20.2",
        port=8728,
        hotspot_network="192.168.88.0/23",
    ),
    RouterDefinition(
        router_id="platinum",
        name="Platinum",
        host="10.20.20.3",
        port=8728,
        hotspot_network="192.168.90.0/23",
    ),
)

ROUTERS: Mapping[str, RouterDefinition] = MappingProxyType(
    {router.router_id: router for router in _ROUTER_DEFINITIONS}
)
DEFAULT_ROUTER_ID = "flint-main"


def get_router(router_id: str) -> RouterDefinition:
    """Resolve only a configured router ID; never interpret it as a host."""

    normalized_router_id = router_id.strip()
    try:
        return ROUTERS[normalized_router_id]
    except KeyError as exc:
        raise UnknownRouterError(
            f"Router '{normalized_router_id}' is not configured."
        ) from exc


def iter_routers() -> Iterator[RouterDefinition]:
    return iter(ROUTERS.values())
