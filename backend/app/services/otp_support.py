from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import AdminRole, AuditActorType, OtpFlow, OtpPurpose
from app.models.otp_limit_reset import OtpLimitReset
from app.models.phone_otp_challenge import PhoneOtpChallenge
from app.schemas.otp_support import OtpLimitResetRequest, OtpUsageResponse
from app.services.otp_limits import as_utc, customer_subject, email_subject, quota_scope


class OtpSupportService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def lookup(self, contact: str, *, now: datetime) -> list[OtpUsageResponse]:
        customers = self.session.scalars(
            select(Customer).where(or_(Customer.email == contact, Customer.phone_number == contact))
        ).all()
        phone_customer_ids = self.session.scalars(
            select(PhoneOtpChallenge.customer_id)
            .where(PhoneOtpChallenge.phone_number == contact)
            .distinct()
        ).all()
        if phone_customer_ids:
            known = {customer.id for customer in customers}
            customers = [
                *customers,
                *self.session.scalars(
                    select(Customer).where(Customer.id.in_(set(phone_customer_ids) - known))
                ).all(),
            ]

        targets = {
            (OtpFlow(purpose.value), email_subject(email))
            for email, purpose in self.session.execute(
                select(EmailOtpChallenge.email, EmailOtpChallenge.purpose)
                .where(
                    or_(
                        EmailOtpChallenge.email == contact,
                        EmailOtpChallenge.phone_number == contact,
                    )
                )
                .distinct()
            )
        }
        for customer in customers:
            targets.update(
                (OtpFlow(purpose.value), email_subject(customer.email)) for purpose in OtpPurpose
            )
            targets.add((OtpFlow.PHONE_VERIFICATION, customer_subject(customer.id)))
        return [self.usage(flow, subject, now=now) for flow, subject in sorted(targets)]

    def usage(self, flow: OtpFlow, subject: str, *, now: datetime) -> OtpUsageResponse:
        email = None
        if flow == OtpFlow.PHONE_VERIFICATION:
            customer = self.session.get(Customer, UUID(subject.removeprefix("customer:")))
            if customer is None:
                raise ServiceError(status.HTTP_404_NOT_FOUND, "OTP subject was not found.")
            identity = (PhoneOtpChallenge.customer_id == customer.id,)
        else:
            email = subject.removeprefix("email:")
            customer = self.session.scalar(select(Customer).where(Customer.email == email))
            identity = (
                EmailOtpChallenge.email == email,
                EmailOtpChallenge.purpose == OtpPurpose(flow.value),
            )

        model, filters = quota_scope(flow, subject)
        latest = self.session.scalar(
            select(model).where(*identity).order_by(model.created_at.desc()).limit(1)
        )
        if customer is None and latest is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "OTP subject was not found.")
        if customer is None and latest is not None and latest.customer_id:
            customer = self.session.get(Customer, latest.customer_id)
        times = [
            as_utc(value)
            for value in self.session.scalars(
                select(model.created_at)
                .where(*filters, model.created_at >= now - timedelta(hours=1))
                .order_by(model.created_at)
            )
        ]
        limit = self.settings.otp_max_requests_per_hour
        retry_at = now
        if times:
            retry_at = max(
                retry_at, times[-1] + timedelta(seconds=self.settings.otp_resend_cooldown_seconds)
            )
        if len(times) >= limit:
            retry_at = max(retry_at, times[-limit] + timedelta(hours=1))

        last_reset = self.session.scalar(
            select(OtpLimitReset)
            .where(OtpLimitReset.flow == flow.value, OtpLimitReset.subject == subject)
            .order_by(OtpLimitReset.reset_at.desc())
            .limit(1)
        )
        # Show the quota's actual destination when older requests belong to an
        # account whose contact information has since changed.
        contact_email = email if email and "@" in email else customer.email if customer else None
        contact_phone = latest.phone_number if latest and latest.phone_number else None
        if not contact_phone:
            contact_phone = (
                customer.phone_number
                if customer
                else email
                if email and email.startswith("+")
                else None
            )
        return OtpUsageResponse(
            flow=flow,
            subject=subject,
            customer_id=customer.id if customer else None,
            username=customer.username if customer else None,
            email=contact_email,
            phone_number=contact_phone,
            requests_used=len(times),
            request_limit=limit,
            requests_remaining=max(0, limit - len(times)),
            last_requested_at=as_utc(latest.created_at) if latest else None,
            next_request_at=retry_at if retry_at > now else None,
            last_reset_at=as_utc(last_reset.reset_at) if last_reset else None,
            last_reset_by=last_reset.admin_email if last_reset else None,
        )

    def reset(
        self, request: OtpLimitResetRequest, admin: AdminUser, *, ip_address: str | None
    ) -> OtpUsageResponse:
        if admin.role != AdminRole.ADMINISTRATOR:
            raise ServiceError(
                status.HTTP_403_FORBIDDEN, "Only administrators can reset OTP limits."
            )
        now = datetime.now(UTC)
        before = self.usage(request.flow, request.subject, now=now)
        reset = OtpLimitReset(
            flow=request.flow.value,
            subject=request.subject,
            admin_user_id=admin.id,
            admin_email=admin.email,
            reset_at=now,
        )
        self.session.add(reset)
        self.session.flush()
        self.session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                customer_id=before.customer_id,
                action="otp.request_limit_reset",
                entity_type="otp_limit_reset",
                entity_id=str(reset.id),
                details={
                    "flow": request.flow.value,
                    "subject": request.subject,
                    "requests_used_before": before.requests_used,
                    "admin_email": admin.email,
                },
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self.session.commit()
        return self.usage(request.flow, request.subject, now=datetime.now(UTC))
