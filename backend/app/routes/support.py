from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.support import SupportSettingsResponse, SupportSettingsUpdate
from app.services.support_settings import SupportSettingsService

router = APIRouter(tags=["support"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]


@router.get("/api/support", response_model=SupportSettingsResponse)
def public_support_settings(session: SessionDependency) -> SupportSettingsResponse:
    return SupportSettingsService(session).get()


@router.get("/api/admin/support", response_model=SupportSettingsResponse)
def admin_support_settings(
    _admin: AdminDependency,
    session: SessionDependency,
) -> SupportSettingsResponse:
    return SupportSettingsService(session).get()


@router.put("/api/admin/support", response_model=SupportSettingsResponse)
def update_support_settings(
    payload: SupportSettingsUpdate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
) -> SupportSettingsResponse:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return SupportSettingsService(session).update(
        payload,
        admin=admin,
        ip_address=request.client.host if request.client else None,
    )
