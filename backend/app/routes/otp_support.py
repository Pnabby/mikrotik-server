from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceError
from app.db.session import get_db_session
from app.models.admin_user import AdminUser
from app.models.enums import AdminRole
from app.routes.admin_auth import get_authenticated_admin
from app.schemas.account import normalize_recovery_identifier
from app.schemas.otp_support import OtpLimitResetRequest, OtpSupportResponse, OtpUsageResponse
from app.services.otp_support import OtpSupportService

router = APIRouter(prefix="/api/admin/otp-support", tags=["admin OTP support"])
SessionDependency = Annotated[Session, Depends(get_db_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
AdminDependency = Annotated[AdminUser, Depends(get_authenticated_admin)]


@router.get("", response_model=OtpSupportResponse)
def lookup_otp_usage(
    session: SessionDependency,
    settings: SettingsDependency,
    admin: AdminDependency,
    search: str = Query(min_length=3, max_length=320),
) -> OtpSupportResponse:
    try:
        contact = normalize_recovery_identifier(search)
    except ValueError as exc:
        raise ServiceError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter a valid email or phone number."
        ) from exc
    now = datetime.now(UTC)
    return OtpSupportResponse(
        items=OtpSupportService(session, settings).lookup(contact, now=now),
        checked_at=now,
        can_reset=admin.role == AdminRole.ADMINISTRATOR,
    )


@router.post("/reset", response_model=OtpUsageResponse)
def reset_otp_limit(
    payload: OtpLimitResetRequest,
    request: Request,
    session: SessionDependency,
    settings: SettingsDependency,
    admin: AdminDependency,
) -> OtpUsageResponse:
    return OtpSupportService(session, settings).reset(
        payload,
        admin,
        ip_address=request.client.host if request.client else None,
    )
