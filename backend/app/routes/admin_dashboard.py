import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.core.security import Argon2PasswordHasher
from app.db.session import get_db_session
from app.dependencies import ROUTER_UNAVAILABLE_DETAIL, mikrotik_client_context
from app.integrations.mikrotik.registry import UnknownRouterError, get_router
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import AccountStatus, AdminRole, AuditActorType, PaymentStatus
from app.models.router import Router
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.admin_dashboard import (
    AdminAccessPointListResponse,
    AdminAnalyticsResponse,
    AdminBroadcastRequest,
    AdminBroadcastResponse,
    AdminCustomerDeleteRequest,
    AdminCustomerDeleteResponse,
    AdminCustomerDirectoryResponse,
    AdminCustomerTransferRequest,
    AdminCustomerTransferResponse,
    AdminCustomerUpdateRequest,
    AdminDashboardResponse,
    AdminNetworkUsageResponse,
    AdminTransactionListResponse,
)
from app.services.account_deletion import AccountDeletionService
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_messaging import AdminMessagingService
from app.services.hostel_transfer import HostelTransferService
from app.services.hostel_transfer_availability import resolve_transfer_routers

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


@router.get("/access-points", response_model=AdminAccessPointListResponse)
def list_access_points(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str = Query(max_length=64),
) -> AdminAccessPointListResponse:
    hostel = session.get(Router, router_id)
    if hostel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).access_points(hostel)


@router.get("/network-usage", response_model=AdminNetworkUsageResponse)
def get_network_usage(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str = Query(max_length=64),
) -> AdminNetworkUsageResponse:
    hostel = session.get(Router, router_id)
    if hostel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).network_usage(hostel)


@router.get("/analytics", response_model=AdminAnalyticsResponse)
def get_analytics(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = Query(default=None, max_length=64),
    days: int = Query(default=30, ge=1, le=3650),
    date_from: date | None = None,
    date_to: date | None = None,
    all_time: bool = False,
    router_hours: int = Query(default=24, ge=24, le=8760),
) -> AdminAnalyticsResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).analytics(
        router_id=router_id,
        days=days,
        date_from=date_from,
        date_to=date_to,
        all_time=all_time,
        router_hours=router_hours,
    )


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
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="joined_at", pattern="^(username|current_plan|last_activity_at|hostel_name|account_status|is_online|joined_at)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> AdminCustomerDirectoryResponse:
    if router_id is not None and session.get(Router, router_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return AdminDashboardService(session).customers_and_devices(
        router_id=router_id,
        account_status=account_status,
        subscription=subscription,
        search=search,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


def _editable_customer(
    customer_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
) -> Customer:
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise ServiceError(status.HTTP_403_FORBIDDEN, "Your role cannot manage customers.")
    customer = session.scalar(
        select(Customer).where(Customer.id == customer_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if customer is None:
        raise ServiceError(status.HTTP_404_NOT_FOUND, "Customer was not found.")
    return customer


@router.patch("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_customer(
    customer_id: uuid.UUID,
    payload: AdminCustomerUpdateRequest,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
) -> None:
    customer = _editable_customer(customer_id, admin, session)
    changed = []
    if customer.email != payload.email:
        customer.email = payload.email
        customer.email_verified_at = None
        changed.append("email")
    if customer.phone_number != payload.phone_number:
        customer.phone_number = payload.phone_number
        customer.phone_verified_at = None
        changed.append("phone_number")
    if changed:
        session.add(AuditLog(
            actor_type=AuditActorType.ADMIN, admin_user_id=admin.id,
            customer_id=customer.id, action="customer.updated_by_admin",
            entity_type="customer", entity_id=str(customer.id),
            details={"fields": changed},
            ip_address=(request.client.host if request.client else "")[:64] or None,
        ))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ServiceError(status.HTTP_409_CONFLICT,
                           "The email or phone number already belongs to another user.") from exc


@router.post(
    "/customers/{customer_id}/transfer-hostel",
    response_model=AdminCustomerTransferResponse,
)
def transfer_customer_hostel(
    customer_id: uuid.UUID,
    payload: AdminCustomerTransferRequest,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
) -> AdminCustomerTransferResponse:
    customer = _editable_customer(customer_id, admin, session)
    source_router, destination_router = resolve_transfer_routers(
        session, customer.router_id, payload.destination_router_id
    )
    with (
        mikrotik_client_context(source_router) as source_client,
        mikrotik_client_context(destination_router) as destination_client,
    ):
        result = HostelTransferService(session).transfer_with_admin_password(
            customer,
            admin=admin,
            password=payload.password.get_secret_value(),
            password_hasher=Argon2PasswordHasher(),
            destination_router_id=destination_router.router_id,
            destination_router_name=destination_router.name,
            source_client=source_client,
            destination_client=destination_client,
            ip_address=request.client.host if request.client else None,
        )
    return AdminCustomerTransferResponse(
        router_id=result.router_id,
        hostel_name=result.router_name,
        remaining_data_limit_bytes=result.remaining_data_limit_bytes,
    )


@router.post(
    "/customers/{customer_id}/delete",
    response_model=AdminCustomerDeleteResponse,
)
def delete_customer(
    customer_id: uuid.UUID,
    payload: AdminCustomerDeleteRequest,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
) -> AdminCustomerDeleteResponse:
    customer = _editable_customer(customer_id, admin, session)
    if not Argon2PasswordHasher().verify(
        admin.password_hash, payload.password.get_secret_value()
    ):
        raise ServiceError(status.HTTP_401_UNAUTHORIZED, "The admin password is incorrect.")
    try:
        source_router = get_router(session, customer.router_id)
    except UnknownRouterError as exc:
        raise ServiceError(status.HTTP_503_SERVICE_UNAVAILABLE, ROUTER_UNAVAILABLE_DETAIL) from exc

    # This audit row intentionally has no customer FK so it survives the same
    # complete data erasure used by customer self-deletion.
    session.add(
        AuditLog(
            actor_type=AuditActorType.ADMIN,
            admin_user_id=admin.id,
            customer_id=None,
            action="customer.deleted_by_admin",
            entity_type="customer",
            entity_id=str(customer.id),
            details={
                "username": customer.username,
                "router_id": customer.router_id,
            },
            ip_address=(request.client.host if request.client else "")[:64] or None,
        )
    )
    try:
        with mikrotik_client_context(source_router) as source_client:
            AccountDeletionService(session).erase(customer, source_client)
    except Exception:
        session.rollback()
        raise
    return AdminCustomerDeleteResponse()


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
