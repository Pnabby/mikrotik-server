import uuid
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ServiceError
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import AuditActorType
from app.models.router import Router
from app.models.support_issue import SupportIssue, SupportIssueReply
from app.schemas.support_issues import (
    IssueCreate,
    IssueListResponse,
    IssueNotificationResponse,
    IssueResponse,
    IssueUpdate,
)


class SupportIssueService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, customer: Customer, payload: IssueCreate) -> IssueResponse:
        # Lock the customer to serialize submission with hostel transfers.
        customer = self.session.scalar(
            select(Customer)
            .where(Customer.id == customer.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if customer is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Customer was not found.")
        hostel = self.session.get(Router, customer.router_id)
        issue = SupportIssue(
            customer_id=customer.id,
            router_id=customer.router_id,
            username=customer.username,
            hostel_name=hostel.name if hostel else "Unknown hostel",
            room_number=payload.room_number or None,
            subject=payload.subject,
            message=payload.message,
            status="open",
            replies=[],
        )
        self.session.add(issue)
        self.session.commit()
        return IssueResponse.model_validate(issue)

    def list(
        self, *, customer_id=None, router_id=None, issue_status=None, offset=0, limit=30
    ) -> IssueListResponse:
        filters = []
        if customer_id is not None:
            filters.append(SupportIssue.customer_id == customer_id)
        if router_id:
            filters.append(SupportIssue.router_id == router_id)
        open_count = (
            self.session.scalar(
                select(func.count())
                .select_from(SupportIssue)
                .where(*filters, SupportIssue.status == "open")
            )
            or 0
        )
        if issue_status:
            filters.append(SupportIssue.status == issue_status)
        total = self.session.scalar(select(func.count()).select_from(SupportIssue).where(*filters))
        issues = self.session.scalars(
            select(SupportIssue)
            .options(selectinload(SupportIssue.replies))
            .where(*filters)
            .order_by(SupportIssue.created_at.desc(), SupportIssue.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return IssueListResponse(
            items=[IssueResponse.model_validate(issue) for issue in issues],
            total=total or 0,
            open_count=open_count,
        )

    def notifications(self) -> IssueNotificationResponse:
        result = self.list(issue_status="open", limit=5)
        return IssueNotificationResponse(count=result.open_count, items=result.items)

    def update(
        self, issue_id: uuid.UUID, payload: IssueUpdate, admin: AdminUser, ip_address: str | None
    ) -> IssueResponse:
        issue = self.session.scalar(
            select(SupportIssue)
            .where(SupportIssue.id == issue_id)
            .with_for_update()
            .options(selectinload(SupportIssue.replies))
        )
        if issue is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Issue was not found.")
        if payload.reply:
            issue.replies.append(SupportIssueReply(admin_user_id=admin.id, message=payload.reply))
        if payload.status:
            if payload.status != issue.status:
                issue.attended_at = datetime.now(UTC) if payload.status == "attended" else None
            issue.status = payload.status
        self.session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                customer_id=issue.customer_id,
                action="support_issue.updated",
                entity_type="support_issue",
                entity_id=str(issue.id),
                details={"status": issue.status, "replied": bool(payload.reply)},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self.session.commit()
        return IssueResponse.model_validate(issue)
