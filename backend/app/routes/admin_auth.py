from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Argon2PasswordHasher
from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.schemas.admin_auth import (
    AdminLoginRequest,
    AdminLogoutResponse,
    AuthenticatedAdminResponse,
)
from app.services.admin_auth import ADMIN_SESSION_COOKIE, AdminAuthenticationService

router = APIRouter(prefix="/api/admin/auth", tags=["admin authentication"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_authenticated_admin(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminUser:
    return AdminAuthenticationService(session, settings).authenticate(
        request.cookies.get(ADMIN_SESSION_COOKIE)
    )


def _response_for(admin: AdminUser) -> AuthenticatedAdminResponse:
    return AuthenticatedAdminResponse(username=admin.email, role=admin.role)


@router.post("/login", response_model=AuthenticatedAdminResponse)
def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthenticatedAdminResponse:
    result = AdminAuthenticationService(session, settings).login(
        payload,
        Argon2PasswordHasher(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        result.token,
        max_age=settings.admin_session_ttl_seconds,
        expires=result.expires_at,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/api/admin",
    )
    return _response_for(result.admin)


@router.get("/session", response_model=AuthenticatedAdminResponse)
def get_session(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthenticatedAdminResponse:
    admin = AdminAuthenticationService(session, settings).authenticate(
        request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    return _response_for(admin)


@router.post("/logout", response_model=AdminLogoutResponse)
def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminLogoutResponse:
    AdminAuthenticationService(session, settings).logout(
        request.cookies.get(ADMIN_SESSION_COOKIE)
    )
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/api/admin")
    return AdminLogoutResponse()
