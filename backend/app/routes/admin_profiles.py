from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.dependencies import MikroTikClientDependency, RouterDependency
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.models.package import PlanGroup
from app.models.router import Router
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_profiles import (
    AdminHostelCreate,
    AdminHostelSummary,
    AdminHostelUpdate,
    AdminPlanGroupCreate,
    AdminPlanGroupResponse,
    AdminPlanGroupUpdate,
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


@router.post(
    "/hostels",
    response_model=AdminHostelSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_hostel(
    payload: AdminHostelCreate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminHostelSummary:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return AdminProfileService(session, settings).create_hostel(
        create=payload,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )


@router.put("/hostels/{router_id}", response_model=AdminHostelSummary)
def update_hostel(
    router_id: str,
    payload: AdminHostelUpdate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminHostelSummary:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    router_model = session.get(Router, router_id)
    if router_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminProfileService(session, settings).update_hostel(
        router=router_model,
        update=payload,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )


@router.post(
    "/hostels/{router_id}/ip-cloud/force-update",
    response_model=AdminHostelSummary,
)
def force_ip_cloud_update(
    request: Request,
    admin: AdminDependency,
    router_definition: RouterDependency,
    router_client: MikroTikClientDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminHostelSummary:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    router_model = session.get(Router, router_definition.router_id)
    assert router_model is not None
    return AdminProfileService(session, settings).force_ip_cloud_update(
        router=router_model,
        router_client=router_client,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )


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


@router.get(
    "/hostels/{router_id}/plan-groups",
    response_model=list[AdminPlanGroupResponse],
)
def list_plan_groups(
    router_id: str,
    _admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> list[AdminPlanGroupResponse]:
    router_model = session.get(Router, router_id)
    if router_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminProfileService(session, settings).list_plan_groups(router_model)


@router.post(
    "/hostels/{router_id}/plan-groups",
    response_model=AdminPlanGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_group(
    router_id: str,
    payload: AdminPlanGroupCreate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminPlanGroupResponse:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    router_model = session.get(Router, router_id)
    if router_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminProfileService(session, settings).create_plan_group(
        router_model,
        payload,
        admin,
        request.client.host if request.client else None,
    )


@router.put(
    "/hostels/{router_id}/plan-groups/{group_id}",
    response_model=AdminPlanGroupResponse,
)
def update_plan_group(
    router_id: str,
    group_id: uuid.UUID,
    payload: AdminPlanGroupUpdate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminPlanGroupResponse:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    group = session.get(PlanGroup, group_id)
    if group is None or group.router_id != router_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminProfileService(session, settings).update_plan_group(
        group,
        payload,
        admin,
        request.client.host if request.client else None,
    )


@router.delete(
    "/hostels/{router_id}/plan-groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_plan_group(
    router_id: str,
    group_id: uuid.UUID,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    group = session.get(PlanGroup, group_id)
    if group is None or group.router_id != router_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    AdminProfileService(session, settings).delete_plan_group(
        group,
        admin,
        request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.delete(
    "/hostels/{router_id}/profiles/{mikrotik_profile}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_router_profile_configuration(
    router_id: str,
    mikrotik_profile: str,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Response:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    router_model = session.get(Router, router_id)
    if router_model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    AdminProfileService(session, settings).delete_profile_configuration(
        router=router_model,
        mikrotik_profile=mikrotik_profile,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
