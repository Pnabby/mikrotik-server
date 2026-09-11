from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.models.enums import AccountStatus, AdminRole, PaymentStatus
from app.models.router import Router
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_dashboard import (
    AdminBroadcastRequest,
    AdminBroadcastResponse,
    AdminCustomerDirectoryResponse,
    AdminDashboardResponse,
    AdminTransactionListResponse,
)
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_messaging import AdminMessagingService

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin dashboard"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


@router.get("", response_model=AdminDashboardResponse)
def get_dashboard(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = Query(default=None, max_length=64),
) -> AdminDashboardResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).summary(router_id)


@router.get("/transactions", response_model=AdminTransactionListResponse)
def list_transactions(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = Query(default=None, max_length=64),
    payment_status: PaymentStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> AdminTransactionListResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).transactions(
        router_id=router_id,
        payment_status=payment_status,
        date_from=date_from,
        date_to=date_to,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.get("/customers", response_model=AdminCustomerDirectoryResponse)
def list_customers_and_devices(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = Query(default=None, max_length=64),
    account_status: AccountStatus | None = None,
    subscription: str = Query(default="all", pattern="^(all|active|inactive)$"),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
) -> AdminCustomerDirectoryResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).customers_and_devices(
        router_id=router_id,
        account_status=account_status,
        subscription=subscription,
        search=search,
        limit=limit,
    )


@router.post("/broadcast", response_model=AdminBroadcastResponse)
def send_broadcast(
    payload: AdminBroadcastRequest,
    admin: AdminDependency,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AdminBroadcastResponse:
    if admin.role == AdminRole.VIEWER:
        raise ServiceError(status.HTTP_403_FORBIDDEN, "Your role cannot send messages.")
    if payload.router_id is not None and session.get(Router, payload.router_id) is None:
        raise ServiceError(status.HTTP_404_NOT_FOUND, "Hostel was not found.")
    result = AdminMessagingService(session, settings).broadcast(
        admin,
        subject=payload.subject,
        message=payload.message,
        router_id=payload.router_id,
    )
    return AdminBroadcastResponse(
        targeted_users=result.targeted_users,
        sms_sent=result.sms_sent,
        email_sent=result.email_sent,
        sms_failed=result.sms_failed,
        email_failed=result.email_failed,
    )
