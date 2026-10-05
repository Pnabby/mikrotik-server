from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.dependencies import MikroTikClientDependency, RouterDependency
from app.integrations.mikrotik.wireguard import WireGuardManager
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_wireguard import (
    RouterRestartRequest,
    WireGuardActionResult,
    WireGuardClientConfig,
    WireGuardCreateResult,
    WireGuardPeerAction,
    WireGuardPeerCreate,
    WireGuardSnapshot,
)
from app.services.admin_wireguard import AdminWireGuardService

router = APIRouter(prefix="/api/admin/hostels", tags=["admin WireGuard"])
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]
SessionDependency = Annotated[Session, Depends(get_db_session)]


def get_vpn_operator(admin: AdminDependency) -> AdminUser:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return admin


OperatorDependency = Annotated[AdminUser, Depends(get_vpn_operator)]


@router.get("/{router_id}/wireguard", response_model=WireGuardSnapshot)
def list_wireguard(
    _admin: AdminDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
) -> WireGuardSnapshot:
    return WireGuardManager(router_client).snapshot(router_definition)


@router.post(
    "/{router_id}/wireguard/peers",
    response_model=WireGuardCreateResult,
    status_code=status.HTTP_201_CREATED,
)
def create_peer(
    payload: WireGuardPeerCreate,
    request: Request,
    admin: OperatorDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
) -> WireGuardCreateResult:
    return AdminWireGuardService(session, WireGuardManager(router_client)).create(
        router_definition.router_id,
        payload,
        admin,
        request.client.host if request.client else None,
    )


@router.post(
    "/{router_id}/wireguard/peers/{target}/client-config", response_model=WireGuardClientConfig
)
def view_client_config(
    target: str,
    request: Request,
    response: Response,
    admin: OperatorDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
) -> WireGuardClientConfig:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return AdminWireGuardService(session, WireGuardManager(router_client)).client_config(
        router_definition.router_id,
        target,
        admin,
        request.client.host if request.client else None,
    )


@router.post("/{router_id}/restart", response_model=WireGuardActionResult)
def restart_router(
    payload: RouterRestartRequest,
    request: Request,
    admin: OperatorDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
) -> WireGuardActionResult:
    return AdminWireGuardService(session, WireGuardManager(router_client)).restart(
        router_definition,
        payload,
        admin,
        request.client.host if request.client else None,
    )


@router.post("/{router_id}/wireguard/peers/{target}/action", response_model=WireGuardActionResult)
def peer_action(
    target: str,
    payload: WireGuardPeerAction,
    request: Request,
    admin: OperatorDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
) -> WireGuardActionResult:
    return AdminWireGuardService(session, WireGuardManager(router_client)).action(
        router_definition.router_id,
        target,
        payload,
        admin,
        request.client.host if request.client else None,
    )
