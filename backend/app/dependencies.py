from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.db.session import get_db_session
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
SessionDependency = Annotated[Session, Depends(get_db_session)]


def resolve_router(router_id: str, session: SessionDependency) -> RouterDefinition:
    try:
        return get_router(session, router_id)
    except UnknownRouterError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Router is not configured.",
        ) from exc


@contextmanager
def mikrotik_client_context(
    router: RouterDefinition,
) -> Generator[MikroTikClient, None, None]:
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
    except (HTTPException, RequestValidationError, ServiceError):
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ROUTER_UNAVAILABLE_DETAIL,
        ) from exc
    finally:
        client.disconnect()


RouterDependency = Annotated[RouterDefinition, Depends(resolve_router)]


def get_mikrotik_client(router: RouterDependency) -> Generator[MikroTikClient, None, None]:
    with mikrotik_client_context(router) as client:
        yield client


MikroTikClientDependency = Annotated[MikroTikClient, Depends(get_mikrotik_client)]


def get_hotspot_service(
    router: RouterDependency,
    client: MikroTikClientDependency,
) -> HotspotService:
    return HotspotService(router, client)
