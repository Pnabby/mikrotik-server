from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import AccountStatus, AuditActorType
from app.services.notifications import CustomerNotificationService


@dataclass(frozen=True, slots=True)
class BroadcastResult:
    targeted_users: int
    sms_sent: int
    email_sent: int
    sms_failed: int
    email_failed: int


class AdminMessagingService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._notifications = CustomerNotificationService(settings)

    def broadcast(
        self,
        admin: AdminUser,
        *,
        subject: str,
        message: str,
        router_id: str | None,
    ) -> BroadcastResult:
        query = select(Customer).where(Customer.account_status != AccountStatus.CLOSED)
        if router_id is not None:
            query = query.where(Customer.router_id == router_id)
        customers = self._session.scalars(query.order_by(Customer.created_at)).all()
        sms_sent = email_sent = sms_failed = email_failed = 0
        for customer in customers:
            result = self._notifications.send(customer, subject=subject, message=message)
            sms_sent += int(result.sms_sent)
            email_sent += int(result.email_sent)
            sms_failed += int(
                bool(customer.phone_number and customer.phone_verified_at) and not result.sms_sent
            )
            email_failed += int(not result.email_sent)
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                action="customer.broadcast_sent",
                entity_type="router" if router_id else "customer_population",
                entity_id=router_id or "all",
                details={
                    "subject": subject,
                    "targeted_users": len(customers),
                    "sms_sent": sms_sent,
                    "email_sent": email_sent,
                    "sms_failed": sms_failed,
                    "email_failed": email_failed,
                },
            )
        )
        self._session.commit()
        return BroadcastResult(
            targeted_users=len(customers),
            sms_sent=sms_sent,
            email_sent=email_sent,
            sms_failed=sms_failed,
            email_failed=email_failed,
        )
