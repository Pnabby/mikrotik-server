from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.models.router import Router
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_dashboard import AdminDashboardResponse
from app.services.admin_dashboard import AdminDashboardService

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin dashboard"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]


@router.get("", response_model=AdminDashboardResponse)
def get_dashboard(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = Query(default=None, max_length=64),
) -> AdminDashboardResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).summary(router_id)

