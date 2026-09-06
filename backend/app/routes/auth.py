from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Argon2PinHasher
from app.db.session import get_db_session
from app.models.customer import Customer
from app.schemas.account import (
    AuthenticatedCustomerResponse,
    CustomerLoginRequest,
    LogoutResponse,
)
from app.services.customer_auth import (
    CUSTOMER_SESSION_COOKIE,
    CustomerAuthenticationService,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_authenticated_customer(
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
) -> Customer:
    return CustomerAuthenticationService(session, settings).authenticate(
        request.cookies.get(CUSTOMER_SESSION_COOKIE)
    )


AuthenticatedCustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]


@router.post("/login", response_model=AuthenticatedCustomerResponse)
def login(
    payload: CustomerLoginRequest,
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthenticatedCustomerResponse:
    result = CustomerAuthenticationService(session, settings).login(
        payload,
        Argon2PinHasher.from_settings(settings),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    cookie_options = {
        "httponly": True,
        "secure": request.url.scheme == "https",
        "samesite": "lax",
        "path": "/",
    }
    if result.persistent:
        cookie_options.update(
            max_age=settings.remembered_customer_session_ttl_seconds,
            expires=result.expires_at,
        )
    response.set_cookie(CUSTOMER_SESSION_COOKIE, result.token, **cookie_options)
    return AuthenticatedCustomerResponse(username=result.customer.username)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> LogoutResponse:
    CustomerAuthenticationService(session, settings).logout(
        request.cookies.get(CUSTOMER_SESSION_COOKIE)
    )
    response.delete_cookie(CUSTOMER_SESSION_COOKIE, path="/")
    return LogoutResponse()
