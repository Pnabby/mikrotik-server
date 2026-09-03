from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class RouterDefinition:
    """Environment-sourced connection and display metadata for an allowed router."""

    router_id: str
    name: str
    host: str
    port: int
    hotspot_network: str


class UnknownRouterError(ValueError):
    """Raised when a router ID is not present in the server-side registry."""


def _configured_routers() -> tuple[RouterDefinition, ...]:
    return tuple(
        RouterDefinition(
            router_id=item.router_id.strip(),
            name=item.name.strip(),
            host=item.host.strip(),
            port=item.port,
            hotspot_network=item.hotspot_network.strip(),
        )
        for item in get_settings().mikrotik_routers_json
        if item.router_id.strip()
    )


class _RouterRegistry(Mapping[str, RouterDefinition]):
    """Read-only mapping that reflects the current cached application settings."""

    def _mapping(self) -> dict[str, RouterDefinition]:
        return {router.router_id: router for router in _configured_routers()}

    def __getitem__(self, key: str) -> RouterDefinition:
        return self._mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())


ROUTERS: Mapping[str, RouterDefinition] = _RouterRegistry()
DEFAULT_ROUTER_ID = "flint-main"


def get_router(router_id: str) -> RouterDefinition:
    """Resolve only a configured router ID; never interpret it as a host."""

    normalized_router_id = router_id.strip()
    try:
        return ROUTERS[normalized_router_id]
    except KeyError as exc:
        raise UnknownRouterError("Router is not configured.") from exc


def iter_routers() -> Iterator[RouterDefinition]:
    return iter(ROUTERS.values())
