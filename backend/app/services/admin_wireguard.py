from collections.abc import Callable
from typing import TypeVar

from fastapi import status
from routeros_api.exceptions import RouterOsApiError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.registry import RouterDefinition
from app.integrations.mikrotik.wireguard import WireGuardManager
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.enums import AuditActorType
from app.schemas.admin_wireguard import (
    RouterRestartRequest,
    WireGuardActionResult,
    WireGuardClientConfig,
    WireGuardCreateResult,
    WireGuardPeerAction,
    WireGuardPeerCreate,
)

Result = TypeVar("Result")


class AdminWireGuardService:
    def __init__(self, session: Session, manager: WireGuardManager):
        self.session = session
        self.manager = manager

    def action(
        self,
        router_id: str,
        target: str,
        payload: WireGuardPeerAction,
        admin: AdminUser,
        ip_address: str | None,
    ) -> WireGuardActionResult:
        return self._audited(
            router_id,
            "wireguard.peer_action",
            {"target": target[:120], **payload.model_dump(exclude_none=True)},
            admin,
            ip_address,
            lambda: self.manager.apply(target, payload),
            "VPN_ACTION_UNCONFIRMED",
        )

    def create(
        self,
        router_id: str,
        payload: WireGuardPeerCreate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> WireGuardCreateResult:
        return self._audited(
            router_id,
            "wireguard.peer_created",
            payload.model_dump(exclude_none=True),
            admin,
            ip_address,
            lambda: self.manager.create(payload),
            "VPN_CREATE_UNCONFIRMED",
        )

    def client_config(
        self,
        router_id: str,
        target: str,
        admin: AdminUser,
        ip_address: str | None,
    ) -> WireGuardClientConfig:
        return self._audited(
            router_id,
            "wireguard.client_config_viewed",
            {"target": target[:120]},
            admin,
            ip_address,
            lambda: self.manager.client_config(target),
            "VPN_CONFIG_EXPORT_FAILED",
        )

    def restart(
        self,
        router: RouterDefinition,
        payload: RouterRestartRequest,
        admin: AdminUser,
        ip_address: str | None,
    ) -> WireGuardActionResult:
        if payload.confirmation != router.name:
            raise ServiceError(
                status.HTTP_400_BAD_REQUEST,
                "Confirm the selected router name.",
                error_code="VPN_RESTART_CONFIRMATION",
            )
        return self._audited(
            router.router_id,
            "router.restart_requested",
            {"router_name": router.name},
            admin,
            ip_address,
            self.manager.restart,
            "VPN_RESTART_UNCONFIRMED",
        )

    def _audited(
        self,
        router_id: str,
        action: str,
        details: dict,
        admin: AdminUser,
        ip_address: str | None,
        operation: Callable[[], Result],
        error_code: str,
    ) -> Result:
        audit = AuditLog(
            actor_type=AuditActorType.ADMIN,
            admin_user_id=admin.id,
            action=action,
            entity_type="router",
            entity_id=router_id,
            details={**details, "outcome": "requested"},
            ip_address=(ip_address or "")[:64] or None,
        )
        # Persist intent before any router mutation, including resets that can
        # interrupt management connectivity. Never store key material in audits.
        self.session.add(audit)
        self.session.commit()
        try:
            result = operation()
        except ServiceError:
            audit.details = {**audit.details, "outcome": "rejected"}
            self.session.commit()
            raise
        except (OSError, RouterOsApiError) as exc:
            audit.details = {**audit.details, "outcome": "unconfirmed"}
            self.session.commit()
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "The router action could not be confirmed. Refresh before retrying.",
                error_code=error_code,
            ) from exc
        audit.details = {
            **audit.details,
            "outcome": "queued" if getattr(result, "queued", False) else "completed",
        }
        if action == "wireguard.peer_created" and result.peer_id:
            audit.details = {**audit.details, "target": result.peer_id}
        self.session.commit()
        return result
