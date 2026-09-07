from __future__ import annotations

from fastapi import status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.enums import AuditActorType
from app.models.support_settings import SupportSettings
from app.schemas.support import SupportSettingsResponse, SupportSettingsUpdate


class SupportSettingsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> SupportSettingsResponse:
        settings = self._session.get(SupportSettings, 1)
        return SupportSettingsResponse(
            phone_number=settings.phone_number if settings else None,
            whatsapp_url=settings.whatsapp_url if settings else None,
        )

    def update(
        self,
        values: SupportSettingsUpdate,
        *,
        admin: AdminUser,
        ip_address: str | None,
    ) -> SupportSettingsResponse:
        settings = self._session.get(SupportSettings, 1)
        if settings is None:
            settings = SupportSettings(id=1)
            self._session.add(settings)
        before = {
            "phone_number": settings.phone_number,
            "whatsapp_url": settings.whatsapp_url,
        }
        settings.phone_number = values.phone_number
        settings.whatsapp_url = values.whatsapp_url
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                action="support_settings.updated",
                entity_type="support_settings",
                entity_id="1",
                details={"before": before, "after": values.model_dump()},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Support settings could not be saved.",
            ) from exc
        return self.get()
