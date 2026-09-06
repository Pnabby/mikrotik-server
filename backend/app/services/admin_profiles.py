from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Protocol

from fastapi import status
from routeros_api.exceptions import RouterOsApiError
from sqlalchemy import Integer, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog
from app.models.enums import AuditActorType, RouterStatus
from app.models.package import Package, RouterPackageProfile
from app.models.router import Router
from app.schemas.admin_profiles import (
    AdminHostelSummary,
    AdminProfileUpdate,
    AdminRouterProfileResponse,
)


class RouterProfileClient(Protocol):
    def get_hotspot_user_profiles(self) -> list[dict[str, str]]: ...


class AdminProfileService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def list_hostels(self) -> list[AdminHostelSummary]:
        routers = self._session.scalars(
            select(Router).order_by(Router.display_order, Router.name, Router.id)
        ).all()
        profile_counts = {
            router_id: (configured, published)
            for router_id, configured, published in self._session.execute(
                select(
                    RouterPackageProfile.router_id,
                    func.count(RouterPackageProfile.id),
                    func.sum(RouterPackageProfile.is_active.cast(Integer)),
                ).group_by(RouterPackageProfile.router_id)
            )
        }
        return [
            AdminHostelSummary(
                router_id=router.id,
                name=router.name,
                location=router.location,
                status=router.status,
                is_active=router.is_active,
                last_seen_at=router.last_seen_at,
                configured_profiles=int(profile_counts.get(router.id, (0, 0))[0] or 0),
                published_profiles=int(profile_counts.get(router.id, (0, 0))[1] or 0),
            )
            for router in routers
        ]

    def list_profiles(
        self,
        router: Router,
        router_client: RouterProfileClient,
    ) -> list[AdminRouterProfileResponse]:
        raw_profiles = self._read_router_profiles(router, router_client)
        live_profiles = {
            name.casefold(): profile
            for profile in raw_profiles
            if (name := _text(profile.get("name")))
        }
        mappings = self._session.scalars(
            select(RouterPackageProfile)
            .options(joinedload(RouterPackageProfile.package))
            .where(RouterPackageProfile.router_id == router.id)
        ).all()
        mappings_by_name = {mapping.mikrotik_profile.casefold(): mapping for mapping in mappings}
        profile_names = sorted(
            set(live_profiles) | set(mappings_by_name),
            key=lambda key: (
                key == self._settings.mikrotik_registration_profile.casefold(),
                key,
            ),
        )

        router.status = RouterStatus.ONLINE
        router.last_seen_at = datetime.now(UTC)
        self._session.commit()
        return [
            self._profile_response(
                profile_name=(
                    _text(live_profiles.get(key, {}).get("name"))
                    or mappings_by_name[key].mikrotik_profile
                ),
                raw_profile=live_profiles.get(key),
                mapping=mappings_by_name.get(key),
            )
            for key in profile_names
        ]

    def save_profile(
        self,
        *,
        router: Router,
        router_client: RouterProfileClient,
        mikrotik_profile: str,
        update: AdminProfileUpdate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminRouterProfileResponse:
        normalized_profile = mikrotik_profile.strip()
        if not normalized_profile or len(normalized_profile) > 120:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router profile was not found.")
        raw_profile = next(
            (
                profile
                for profile in self._read_router_profiles(router, router_client)
                if _text(profile.get("name")).casefold() == normalized_profile.casefold()
            ),
            None,
        )
        if raw_profile is None:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router profile was not found.")
        canonical_name = _text(raw_profile.get("name"))
        if (
            canonical_name.casefold()
            == self._settings.mikrotik_registration_profile.casefold()
            and update.is_visible
        ):
            raise ServiceError(
                status.HTTP_400_BAD_REQUEST,
                "The registration profile cannot be published for purchase.",
            )

        mapping = self._session.scalar(
            select(RouterPackageProfile)
            .options(joinedload(RouterPackageProfile.package))
            .where(
                RouterPackageProfile.router_id == router.id,
                func.lower(RouterPackageProfile.mikrotik_profile) == canonical_name.casefold(),
            )
            .limit(1)
        )
        action = "router_profile.updated"
        if mapping is None:
            package = Package(
                code=self._available_package_code(router.id, canonical_name),
                name=update.display_name,
                description=update.description,
                amount=update.amount,
                currency=update.currency,
                duration_seconds=update.duration_seconds,
                data_limit_bytes=update.data_limit_bytes,
                device_limit=update.device_limit,
                is_promotional=update.is_promotional,
                is_active=update.is_visible,
            )
            mapping = RouterPackageProfile(
                router=router,
                package=package,
                mikrotik_profile=canonical_name,
            )
            self._session.add(mapping)
            action = "router_profile.configured"
        else:
            package = self._isolate_shared_package(mapping)

        mapping.display_name = update.display_name
        mapping.description = update.description
        mapping.download_speed = update.download_speed
        mapping.is_active = update.is_visible
        package.name = update.display_name
        package.description = update.description
        package.amount = update.amount
        package.currency = update.currency
        package.duration_seconds = update.duration_seconds
        package.data_limit_bytes = update.data_limit_bytes
        package.device_limit = update.device_limit
        package.is_promotional = update.is_promotional
        package.is_active = update.is_visible
        router.status = RouterStatus.ONLINE
        router.last_seen_at = datetime.now(UTC)
        try:
            self._session.flush()
            self._session.add(
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    admin_user_id=admin.id,
                    action=action,
                    entity_type="router_package_profile",
                    entity_id=str(mapping.id),
                    details={
                        "router_id": router.id,
                        "mikrotik_profile": canonical_name,
                        "display_name": update.display_name,
                        "is_visible": update.is_visible,
                        "amount": str(update.amount),
                        "currency": update.currency,
                        "duration_seconds": update.duration_seconds,
                        "download_speed": update.download_speed,
                        "is_promotional": update.is_promotional,
                    },
                    ip_address=(ip_address or "")[:64] or None,
                )
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "This router profile is already configured.",
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The router profile could not be saved.",
            ) from exc
        return self._profile_response(
            profile_name=canonical_name,
            raw_profile=raw_profile,
            mapping=mapping,
        )

    def _profile_response(
        self,
        *,
        profile_name: str,
        raw_profile: dict[str, str] | None,
        mapping: RouterPackageProfile | None,
    ) -> AdminRouterProfileResponse:
        package = mapping.package if mapping is not None else None
        return AdminRouterProfileResponse(
            mikrotik_profile=profile_name,
            display_name=(mapping.display_name or package.name) if mapping and package else None,
            description=(mapping.description or package.description) if mapping and package else None,
            package_id=package.id if package else None,
            amount=package.amount if package else None,
            currency=package.currency if package else "GHS",
            duration_seconds=package.duration_seconds if package else None,
            data_limit_bytes=package.data_limit_bytes if package else None,
            device_limit=package.device_limit if package else _positive_int(raw_profile, "shared-users"),
            download_speed=(
                mapping.download_speed
                if mapping and mapping.download_speed
                else _download_speed(_profile_value(raw_profile, "rate-limit"))
            ),
            is_promotional=bool(package and package.is_promotional),
            is_configured=mapping is not None,
            is_visible=bool(mapping and mapping.is_active and package and package.is_active),
            is_registration_profile=(
                profile_name.casefold()
                == self._settings.mikrotik_registration_profile.casefold()
            ),
            available_on_router=raw_profile is not None,
            rate_limit=_profile_value(raw_profile, "rate-limit"),
            shared_users=_positive_int(raw_profile, "shared-users"),
            session_timeout=_profile_value(raw_profile, "session-timeout"),
            idle_timeout=_profile_value(raw_profile, "idle-timeout"),
            address_pool=_profile_value(raw_profile, "address-pool"),
        )

    def _isolate_shared_package(self, mapping: RouterPackageProfile) -> Package:
        package = mapping.package
        reference_count = self._session.scalar(
            select(func.count(RouterPackageProfile.id)).where(
                RouterPackageProfile.package_id == package.id
            )
        )
        if int(reference_count or 0) <= 1:
            return package
        isolated = Package(
            code=self._available_package_code(mapping.router_id, mapping.mikrotik_profile),
            name=package.name,
            description=package.description,
            amount=package.amount,
            currency=package.currency,
            duration_seconds=package.duration_seconds,
            data_limit_bytes=package.data_limit_bytes,
            device_limit=package.device_limit,
            is_promotional=package.is_promotional,
            is_active=package.is_active,
        )
        mapping.package = isolated
        self._session.add(isolated)
        return isolated

    def _available_package_code(self, router_id: str, profile_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", f"{router_id}-{profile_name}".casefold()).strip("-")
        digest = hashlib.sha256(f"{router_id}:{profile_name}".encode()).hexdigest()[:8]
        base = (slug or "router-profile")[:70]
        candidate = base
        counter = 1
        while self._session.scalar(select(Package.id).where(Package.code == candidate)):
            suffix = digest if counter == 1 else f"{digest}-{counter}"
            candidate = f"{base[: 79 - len(suffix)]}-{suffix}"
            counter += 1
        return candidate

    def _read_router_profiles(
        self,
        router: Router,
        router_client: RouterProfileClient,
    ) -> list[dict[str, str]]:
        try:
            return router_client.get_hotspot_user_profiles()
        except (OSError, RouterOsApiError):
            router.status = RouterStatus.OFFLINE
            self._session.commit()
            raise


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _profile_value(profile: dict[str, str] | None, key: str) -> str | None:
    value = _text(profile.get(key)) if profile else ""
    return value or None


def _download_speed(rate_limit: str | None) -> str | None:
    """Return the client download portion of a RouterOS rx/tx rate limit."""
    limit_parts = (rate_limit or "").split(maxsplit=1)
    if not limit_parts:
        return None
    primary_limit = limit_parts[0]
    rates = primary_limit.split("/")
    raw_speed = rates[1] if len(rates) > 1 and rates[1] else rates[0]
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmMgG]?)", raw_speed.strip())
    if not match or float(match.group(1)) <= 0:
        return None
    value, suffix = match.groups()
    unit = {"k": "Kbps", "m": "Mbps", "g": "Gbps", "": "bps"}[suffix.casefold()]
    return f"{value} {unit}"


def _positive_int(profile: dict[str, str] | None, key: str) -> int | None:
    value = _profile_value(profile, key)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
