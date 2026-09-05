from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.dependencies import MikroTikClientDependency, RouterDependency
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.models.router import Router
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_profiles import (
    AdminHostelSummary,
    AdminProfileUpdate,
    AdminRouterProfileResponse,
)
from app.services.admin_profiles import AdminProfileService

router = APIRouter(prefix="/api/admin", tags=["admin profile catalogue"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]


@router.get("/hostels", response_model=list[AdminHostelSummary])
def list_hostels(
    _admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> list[AdminHostelSummary]:
    return AdminProfileService(session, settings).list_hostels()


@router.get(
    "/hostels/{router_id}/profiles",
    response_model=list[AdminRouterProfileResponse],
)
def list_router_profiles(
    _admin: AdminDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> list[AdminRouterProfileResponse]:
    router_model = session.get(Router, router_definition.router_id)
    assert router_model is not None
    return AdminProfileService(session, settings).list_profiles(router_model, router_client)


@router.put(
    "/hostels/{router_id}/profiles/{mikrotik_profile}",
    response_model=AdminRouterProfileResponse,
)
def save_router_profile(
    mikrotik_profile: str,
    payload: AdminProfileUpdate,
    request: Request,
    admin: AdminDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminRouterProfileResponse:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    router_model = session.get(Router, router_definition.router_id)
    assert router_model is not None
    return AdminProfileService(session, settings).save_profile(
        router=router_model,
        router_client=router_client,
        mikrotik_profile=mikrotik_profile,
        update=payload,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )
