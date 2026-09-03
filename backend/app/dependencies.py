from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError

from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import (
    RouterDefinition,
    UnknownRouterError,
    get_router,
)
from app.services.hotspot import HotspotService


ROUTER_UNAVAILABLE_DETAIL = (
    "The router service is temporarily unavailable. Please try again later."
)


def resolve_router(router_id: str) -> RouterDefinition:
    try:
        return get_router(router_id)
    except UnknownRouterError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Router is not configured.",
        ) from exc


@contextmanager
def _client_context(router: RouterDefinition) -> Generator[MikroTikClient, None, None]:
    try:
        config = MikroTikConfig.from_env(router)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Router service is not configured.",
        ) from exc

    client = MikroTikClient(config)
    try:
        yield client
    except (HTTPException, RequestValidationError):
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ROUTER_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        client.disconnect()


def get_mikrotik_client(
    router: RouterDefinition = Depends(resolve_router),
) -> Generator[MikroTikClient, None, None]:
    with _client_context(router) as client:
        yield client


def get_hotspot_service(
    router: RouterDefinition = Depends(resolve_router),
    client: MikroTikClient = Depends(get_mikrotik_client),
) -> HotspotService:
    return HotspotService(router, client)
