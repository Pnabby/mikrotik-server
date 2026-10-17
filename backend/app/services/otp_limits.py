from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.enums import OtpFlow, OtpPurpose
from app.models.otp_limit_reset import OtpLimitReset
from app.models.phone_otp_challenge import PhoneOtpChallenge


def email_subject(email: str) -> str:
    return f"email:{email}"


def customer_subject(customer_id: UUID) -> str:
    return f"customer:{customer_id}"


def quota_scope(flow: OtpFlow, subject: str):
    """The same quota identity and reset boundary serve enforcement and admin reporting."""
    if flow == OtpFlow.PHONE_VERIFICATION:
        model = PhoneOtpChallenge
        identity = (model.customer_id == UUID(subject.removeprefix("customer:")),)
    else:
        model = EmailOtpChallenge
        identity = (
            model.email == subject.removeprefix("email:"),
            model.purpose == OtpPurpose(flow.value),
        )
    cutoff = (
        select(func.max(OtpLimitReset.reset_at))
        .where(OtpLimitReset.flow == flow.value, OtpLimitReset.subject == subject)
        .scalar_subquery()
    )
    return model, (
        *identity,
        model.created_at > func.coalesce(cutoff, datetime(1970, 1, 1, tzinfo=UTC)),
    )


def enforce_otp_request_limit(
    session: Session, settings: Settings, flow: OtpFlow, subject: str, *, now: datetime
) -> None:
    model, filters = quota_scope(flow, subject)
    latest = session.scalar(
        select(model.created_at).where(*filters).order_by(model.created_at.desc()).limit(1)
    )
    if (
        latest is not None
        and (now - as_utc(latest)).total_seconds() < settings.otp_resend_cooldown_seconds
    ):
        raise ServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS, "Please wait before requesting another code."
        )
    used = session.scalar(
        select(func.count())
        .select_from(model)
        .where(*filters, model.created_at >= now - timedelta(hours=1))
    )
    if (used or 0) >= settings.otp_max_requests_per_hour:
        raise ServiceError(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many verification codes requested."
        )


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
