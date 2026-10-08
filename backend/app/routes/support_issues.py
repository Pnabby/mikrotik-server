import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.models.customer import Customer
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.routes.auth import get_authenticated_customer
from app.schemas.support_issues import (
    IssueCreate,
    IssueListResponse,
    IssueNotificationResponse,
    IssueResponse,
    IssueUpdate,
)
from app.services.support_issues import SupportIssueService

router = APIRouter(tags=["support issues"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
CustomerDependency = Annotated[Customer, Depends(get_authenticated_customer)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]


@router.post("/api/account/issues", response_model=IssueResponse, status_code=201)
def create_issue(payload: IssueCreate, customer: CustomerDependency, session: SessionDependency):
    return SupportIssueService(session).create(customer, payload)


@router.get("/api/account/issues", response_model=IssueListResponse)
def customer_issues(
    customer: CustomerDependency,
    session: SessionDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return SupportIssueService(session).list(customer_id=customer.id, offset=offset)


@router.get("/api/admin/notifications", response_model=IssueNotificationResponse)
def notifications(_admin: AdminDependency, session: SessionDependency):
    return SupportIssueService(session).notifications()


@router.get("/api/admin/issues", response_model=IssueListResponse)
def admin_issues(
    _admin: AdminDependency,
    session: SessionDependency,
    router_id: str | None = None,
    issue_status: Literal["open", "attended"] | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return SupportIssueService(session).list(
        router_id=router_id,
        issue_status=issue_status,
        offset=offset,
    )


@router.put("/api/admin/issues/{issue_id}", response_model=IssueResponse)
def update_issue(
    issue_id: uuid.UUID,
    payload: IssueUpdate,
    request: Request,
    admin: AdminDependency,
    session: SessionDependency,
):
    if admin.role not in {AdminRole.OPERATOR, AdminRole.ADMINISTRATOR}:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return SupportIssueService(session).update(
        issue_id,
        payload,
        admin,
        request.client.host if request.client else None,
    )
