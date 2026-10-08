from __future__ import annotations

import hashlib
import re
import uuid
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
from app.models.package import Package, PlanGroup, RouterPackageProfile
from app.models.router import Router
from app.schemas.admin_profiles import (
    AdminBulkPlanGroupResponse,
    AdminHostelCreate,
    AdminHostelSummary,
    AdminHostelUpdate,
    AdminPlanGroupCreate,
    AdminPlanGroupResponse,
    AdminPlanGroupUpdate,
    AdminProfileUpdate,
    AdminRouterProfileResponse,
)
from app.services.profile_settings import profile_differences


class RouterProfileClient(Protocol):
    def get_hotspot_user_profiles(self) -> list[dict[str, str]]: ...

    def configure_hotspot_user_profile(
        self, name: str, settings: dict[str, str], *, template: dict[str, str] | None = None
    ) -> dict[str, str]: ...

    def force_ip_cloud_update(self) -> None: ...


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
            self._hostel_response(router, profile_counts.get(router.id, (0, 0)))
            for router in routers
        ]

    def force_ip_cloud_update(
        self,
        *,
        router: Router,
        router_client: RouterProfileClient,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminHostelSummary:
        """Run the RouterOS IP Cloud force-update action for one hostel."""
        try:
            router_client.force_ip_cloud_update()
        except (OSError, RouterOsApiError):
            router.status = RouterStatus.OFFLINE
            self._session.commit()
            raise

        router.status = RouterStatus.ONLINE
        router.last_seen_at = datetime.now(UTC)
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                action="router.ip_cloud_force_updated",
                entity_type="router",
                entity_id=router.id,
                details={"router_id": router.id},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._session.commit()
        counts = self._session.execute(
            select(
                func.count(RouterPackageProfile.id),
                func.sum(RouterPackageProfile.is_active.cast(Integer)),
            ).where(RouterPackageProfile.router_id == router.id)
        ).one()
        return self._hostel_response(router, counts)

    def update_hostel(
        self,
        *,
        router: Router,
        update: AdminHostelUpdate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminHostelSummary:
        before = {
            "name": router.name,
            "location": router.location,
            "vpn_host": router.vpn_host,
            "api_port": router.api_port,
            "hotspot_network": router.hotspot_network,
            "paystack_split_code": router.paystack_split_code,
            "display_order": router.display_order,
            "is_active": router.is_active,
        }
        router.name = update.name
        router.location = update.location
        router.vpn_host = update.vpn_host
        router.api_port = update.api_port
        router.hotspot_network = update.hotspot_network
        router.paystack_split_code = update.paystack_split_code
        router.display_order = update.display_order
        router.is_active = update.is_active
        try:
            self._session.add(
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    admin_user_id=admin.id,
                    action="router.updated",
                    entity_type="router",
                    entity_id=router.id,
                    details={"before": before, "after": update.model_dump()},
                    ip_address=(ip_address or "")[:64] or None,
                )
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "Another hostel already uses this VPN host.",
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The hostel details could not be saved.",
            ) from exc
        counts = self._session.execute(
            select(
                func.count(RouterPackageProfile.id),
                func.sum(RouterPackageProfile.is_active.cast(Integer)),
            ).where(RouterPackageProfile.router_id == router.id)
        ).one()
        return self._hostel_response(router, counts)

    def create_hostel(
        self,
        *,
        create: AdminHostelCreate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminHostelSummary:
        router = Router(
            id=create.router_id,
            name=create.name,
            location=create.location,
            vpn_host=create.vpn_host,
            api_port=create.api_port,
            hotspot_network=create.hotspot_network,
            paystack_split_code=create.paystack_split_code,
            display_order=create.display_order,
            is_active=create.is_active,
        )
        self._session.add(router)
        try:
            self._session.flush()
            self._session.add(
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    admin_user_id=admin.id,
                    action="router.created",
                    entity_type="router",
                    entity_id=router.id,
                    details={"after": create.model_dump()},
                    ip_address=(ip_address or "")[:64] or None,
                )
            )
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A hostel with this ID or VPN host already exists.",
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The hostel could not be created.",
            ) from exc
        return self._hostel_response(router, (0, 0))

    @staticmethod
    def _hostel_response(router: Router, counts: tuple[object, object]) -> AdminHostelSummary:
        return AdminHostelSummary(
            router_id=router.id,
            name=router.name,
            location=router.location,
            vpn_host=router.vpn_host,
            api_port=router.api_port,
            hotspot_network=router.hotspot_network,
            paystack_split_code=router.paystack_split_code,
            display_order=router.display_order,
            status=router.status,
            is_active=router.is_active,
            last_seen_at=router.last_seen_at,
            configured_profiles=int(counts[0] or 0),
            published_profiles=int(counts[1] or 0),
        )

    def list_profiles(
        self,
        router: Router,
        router_client: RouterProfileClient,
    ) -> list[AdminRouterProfileResponse]:
        raw_profiles = self._read_router_profiles(router, router_client)
        live_profiles = {
            name: profile
            for profile in raw_profiles
            if (name := _text(profile.get("name")))
        }
        mappings = self._session.scalars(
            select(RouterPackageProfile)
            .options(
                joinedload(RouterPackageProfile.package),
                joinedload(RouterPackageProfile.group),
            )
            .where(RouterPackageProfile.router_id == router.id)
        ).all()
        mappings_by_name = {mapping.mikrotik_profile: mapping for mapping in mappings}
        profile_names = sorted(
            set(live_profiles) | set(mappings_by_name),
            key=lambda key: (
                key.casefold() == self._settings.mikrotik_registration_profile.casefold(),
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
        source_profile: dict[str, str] | None = None,
    ) -> AdminRouterProfileResponse:
        normalized_profile = mikrotik_profile.strip()
        if not normalized_profile or len(normalized_profile) > 120:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router profile was not found.")
        raw_profile = next(
            (
                profile
                for profile in self._read_router_profiles(router, router_client)
                if _text(profile.get("name")) == normalized_profile
            ),
            None,
        )
        if raw_profile is None and not (source_profile and update.router_settings):
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router profile was not found.")
        canonical_name = _text(raw_profile.get("name")) if raw_profile else normalized_profile
        if (
            canonical_name.casefold() == self._settings.mikrotik_registration_profile.casefold()
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
                RouterPackageProfile.mikrotik_profile == canonical_name,
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

        # Validate the catalogue before touching RouterOS.
        if update.group_id is not None and self._session.scalar(
            select(PlanGroup.id).where(PlanGroup.id == update.group_id, PlanGroup.router_id == router.id)
        ) is None:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "Invalid plan group.")
        if update.router_settings is not None:
            try:
                raw_profile = router_client.configure_hotspot_user_profile(
                    canonical_name, update.router_settings.router_values(), template=source_profile,
                )
                if profile_differences(update.router_settings.router_values(), raw_profile):
                    raise RuntimeError("Router profile read-back did not match the requested settings.")
            except Exception as exc:
                raise ServiceError(
                    status.HTTP_502_BAD_GATEWAY, "Router settings could not be confirmed.",
                    error_code="profile_settings_unconfirmed",
                ) from exc

        mapping.display_name = update.display_name
        mapping.description = update.description
        mapping.download_speed = (
            _download_speed(_profile_value(raw_profile, "rate-limit"))
            if update.router_settings is not None else update.download_speed
        )
        mapping.is_active = update.is_visible
        if "group_id" in update.model_fields_set:
            if update.group_id is None:
                mapping.group = None
            else:
                group = self._session.scalar(
                    select(PlanGroup).where(
                        PlanGroup.id == update.group_id,
                        PlanGroup.router_id == router.id,
                    )
                )
                if group is None:
                    raise ServiceError(
                        status.HTTP_400_BAD_REQUEST,
                        "The selected plan group does not belong to this hostel.",
                    )
                mapping.group = group
        package.name = update.display_name
        package.description = update.description
        package.amount = update.amount
        package.currency = update.currency
        package.duration_seconds = update.duration_seconds
        package.data_limit_bytes = update.data_limit_bytes
        package.device_limit = (
            update.router_settings.shared_users if update.router_settings else update.device_limit
        )
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
                        "group_id": str(mapping.group_id) if mapping.group_id else None,
                        "router_settings": update.router_settings.model_dump()
                        if update.router_settings else None,
                        "source_router_id": update.source_router_id,
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

    def delete_profile_configuration(
        self,
        *,
        router: Router,
        mikrotik_profile: str,
        admin: AdminUser,
        ip_address: str | None,
    ) -> None:
        """Remove the local plan mapping without changing the RouterOS profile."""
        normalized_profile = mikrotik_profile.strip()
        if not normalized_profile or len(normalized_profile) > 120:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Router profile was not found.")

        mapping = self._session.scalar(
            select(RouterPackageProfile)
            .where(
                RouterPackageProfile.router_id == router.id,
                RouterPackageProfile.mikrotik_profile == normalized_profile,
            )
            .limit(1)
        )
        # Treat an already-unconfigured profile as success so bulk removal can
        # safely target every hostel and retries remain idempotent.
        if mapping is None:
            return

        mapping_id = str(mapping.id)
        package_id = str(mapping.package_id)
        canonical_name = mapping.mikrotik_profile
        try:
            self._session.delete(mapping)
            self._session.add(
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    admin_user_id=admin.id,
                    action="router_profile.configuration_deleted",
                    entity_type="router_package_profile",
                    entity_id=mapping_id,
                    details={
                        "router_id": router.id,
                        "mikrotik_profile": canonical_name,
                        "package_id": package_id,
                        "router_profile_deleted": False,
                    },
                    ip_address=(ip_address or "")[:64] or None,
                )
            )
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The router profile configuration could not be deleted.",
            ) from exc

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
            description=(mapping.description or package.description)
            if mapping and package
            else None,
            package_id=package.id if package else None,
            group_id=mapping.group_id if mapping else None,
            amount=package.amount if package else None,
            currency=package.currency if package else "GHS",
            duration_seconds=package.duration_seconds if package else None,
            data_limit_bytes=package.data_limit_bytes if package else None,
            device_limit=package.device_limit if package else None,
            download_speed=(
                mapping.download_speed
                if mapping and mapping.download_speed
                else _download_speed(_profile_value(raw_profile, "rate-limit"))
            ),
            is_promotional=bool(package and package.is_promotional),
            is_configured=mapping is not None,
            is_visible=bool(mapping and mapping.is_active and package and package.is_active),
            is_registration_profile=(
                profile_name.casefold() == self._settings.mikrotik_registration_profile.casefold()
            ),
            available_on_router=raw_profile is not None,
            rate_limit=_profile_value(raw_profile, "rate-limit"),
            shared_users=_positive_int(raw_profile, "shared-users"),
            session_timeout=_profile_value(raw_profile, "session-timeout"),
            idle_timeout=_profile_value(raw_profile, "idle-timeout"),
            address_pool=_profile_value(raw_profile, "address-pool"),
            keepalive_timeout=_profile_value(raw_profile, "keepalive-timeout"),
        )

    def list_plan_groups(self, router: Router) -> list[AdminPlanGroupResponse]:
        groups = self._session.scalars(
            select(PlanGroup)
            .where(PlanGroup.router_id == router.id)
            .order_by(PlanGroup.display_order, PlanGroup.name)
        ).all()
        profile_names: dict[uuid.UUID, list[str]] = {}
        for group_id, profile_name in self._session.execute(
            select(RouterPackageProfile.group_id, RouterPackageProfile.mikrotik_profile).where(
                RouterPackageProfile.router_id == router.id,
                RouterPackageProfile.group_id.is_not(None),
            )
        ):
            if group_id is not None:
                profile_names.setdefault(group_id, []).append(profile_name)
        return [
            self._plan_group_response(group, profile_names.get(group.id, [])) for group in groups
        ]

    def create_plan_group(
        self,
        router: Router,
        create: AdminPlanGroupCreate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminPlanGroupResponse:
        group = PlanGroup(router=router, **create.model_dump(exclude={"profile_names"}))
        self._session.add(group)
        self._save_plan_group(
            group,
            create.profile_names,
            admin,
            "plan_group.created",
            ip_address,
        )
        return self._plan_group_response(group, create.profile_names)

    def update_plan_group(
        self,
        group: PlanGroup,
        update: AdminPlanGroupUpdate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminPlanGroupResponse:
        for field, value in update.model_dump(exclude={"profile_names"}).items():
            setattr(group, field, value)
        self._save_plan_group(
            group,
            update.profile_names,
            admin,
            "plan_group.updated",
            ip_address,
        )
        return self._plan_group_response(group, update.profile_names)

    def delete_plan_group(
        self,
        group: PlanGroup,
        admin: AdminUser,
        ip_address: str | None,
    ) -> None:
        group_id = group.id
        self._session.delete(group)
        self._session.add(
            AuditLog(
                actor_type=AuditActorType.ADMIN,
                admin_user_id=admin.id,
                action="plan_group.deleted",
                entity_type="plan_group",
                entity_id=str(group_id),
                details={"router_id": group.router_id, "name": group.name},
                ip_address=(ip_address or "")[:64] or None,
            )
        )
        self._session.commit()

    def list_bulk_plan_groups(self, routers: list[Router]) -> list[AdminBulkPlanGroupResponse]:
        if not routers:
            return []
        router_ids = {router.id for router in routers}
        groups = self._session.scalars(
            select(PlanGroup)
            .where(PlanGroup.router_id.in_(router_ids))
            .order_by(PlanGroup.display_order, PlanGroup.name)
        ).all()
        names_by_group: dict[uuid.UUID, list[str]] = {}
        for group_id, profile_name in self._session.execute(
            select(RouterPackageProfile.group_id, RouterPackageProfile.mikrotik_profile).where(
                RouterPackageProfile.router_id.in_(router_ids),
                RouterPackageProfile.group_id.is_not(None),
            )
        ):
            if group_id is not None:
                names_by_group.setdefault(group_id, []).append(profile_name)

        groups_by_key: dict[str, list[PlanGroup]] = {}
        for group in groups:
            groups_by_key.setdefault(group.name.casefold(), []).append(group)

        responses: list[AdminBulkPlanGroupResponse] = []
        for key, matching_groups in groups_by_key.items():
            representative = matching_groups[0]
            group_key = self._bulk_group_key(key)
            settings = {
                (
                    group.name,
                    group.description,
                    group.display_order,
                    group.sort_by_price,
                )
                for group in matching_groups
            }
            assignments = [
                {name.casefold(): name for name in names_by_group.get(group.id, [])}
                for group in matching_groups
            ]
            common_keys = set(assignments[0]) if assignments else set()
            for assigned in assignments[1:]:
                common_keys.intersection_update(assigned)
            if len(matching_groups) != len(routers):
                common_keys.clear()
            common_names = sorted(
                (assignments[0][name] for name in common_keys), key=str.casefold
            )
            responses.append(
                AdminBulkPlanGroupResponse(
                    id=group_key,
                    group_key=group_key,
                    name=representative.name,
                    description=representative.description,
                    display_order=representative.display_order,
                    sort_by_price=representative.sort_by_price,
                    profile_names=common_names,
                    plan_count=len(common_names),
                    hostel_count=len(routers),
                    configured_hostels=len({group.router_id for group in matching_groups}),
                    settings_consistent=(
                        len(matching_groups) == len(routers)
                        and len(settings) == 1
                        and all(set(assigned) == set(assignments[0]) for assigned in assignments)
                    ),
                )
            )
        return sorted(responses, key=lambda item: (item.display_order, item.name.casefold()))

    def create_bulk_plan_group(
        self,
        routers: list[Router],
        create: AdminPlanGroupCreate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminBulkPlanGroupResponse:
        if not routers:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "No active hostels are available.")
        existing_names = {
            group.name.casefold()
            for group in self._session.scalars(
                select(PlanGroup).where(PlanGroup.router_id.in_([router.id for router in routers]))
            )
        }
        if create.name.casefold() in existing_names:
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A plan group with this name already exists in at least one hostel.",
            )
        self._save_bulk_plan_groups(
            routers=routers,
            existing_by_router={},
            update=create,
            admin=admin,
            action="plan_group.bulk_created",
            ip_address=ip_address,
        )
        return self._find_bulk_group(routers, create.name)

    def update_bulk_plan_group(
        self,
        routers: list[Router],
        group_key: str,
        update: AdminPlanGroupUpdate,
        admin: AdminUser,
        ip_address: str | None,
    ) -> AdminBulkPlanGroupResponse:
        if not routers:
            raise ServiceError(status.HTTP_400_BAD_REQUEST, "No active hostels are available.")
        normalized_key = group_key.strip().casefold()
        matching = [
            group
            for group in self._session.scalars(
                select(PlanGroup).where(PlanGroup.router_id.in_([router.id for router in routers]))
            )
            if self._bulk_group_key(group.name) == normalized_key
        ]
        if not matching:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Plan group was not found.")
        existing_by_router = {group.router_id: group for group in matching}
        self._save_bulk_plan_groups(
            routers=routers,
            existing_by_router=existing_by_router,
            update=update,
            admin=admin,
            action="plan_group.bulk_updated",
            ip_address=ip_address,
        )
        return self._find_bulk_group(routers, update.name)

    def delete_bulk_plan_group(
        self,
        routers: list[Router],
        group_key: str,
        admin: AdminUser,
        ip_address: str | None,
    ) -> None:
        normalized_key = group_key.strip().casefold()
        groups = [
            group
            for group in self._session.scalars(
                select(PlanGroup).where(PlanGroup.router_id.in_([router.id for router in routers]))
            )
            if self._bulk_group_key(group.name) == normalized_key
        ]
        if not groups:
            raise ServiceError(status.HTTP_404_NOT_FOUND, "Plan group was not found.")
        try:
            for group in groups:
                self._session.delete(group)
                self._session.add(
                    AuditLog(
                        actor_type=AuditActorType.ADMIN,
                        admin_user_id=admin.id,
                        action="plan_group.bulk_deleted",
                        entity_type="plan_group",
                        entity_id=str(group.id),
                        details={"router_id": group.router_id, "name": group.name},
                        ip_address=(ip_address or "")[:64] or None,
                    )
                )
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Plan groups could not be deleted.",
            ) from exc

    def _save_bulk_plan_groups(
        self,
        *,
        routers: list[Router],
        existing_by_router: dict[str, PlanGroup],
        update: AdminPlanGroupCreate,
        admin: AdminUser,
        action: str,
        ip_address: str | None,
    ) -> None:
        try:
            for router in routers:
                group = existing_by_router.get(router.id)
                if group is None:
                    group = PlanGroup(router=router)
                    self._session.add(group)
                group.name = update.name
                group.description = update.description
                group.display_order = update.display_order
                group.sort_by_price = update.sort_by_price
                self._session.flush()
                assigned = self._assign_group_profiles(group, update.profile_names)
                self._session.add(
                    AuditLog(
                        actor_type=AuditActorType.ADMIN,
                        admin_user_id=admin.id,
                        action=action,
                        entity_type="plan_group",
                        entity_id=str(group.id),
                        details={
                            "router_id": router.id,
                            "name": group.name,
                            "profile_names": assigned,
                        },
                        ip_address=(ip_address or "")[:64] or None,
                    )
                )
            self._session.commit()
        except ServiceError:
            self._session.rollback()
            raise
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A group with this name conflicts with an existing hostel group.",
            ) from exc
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Plan groups could not be saved.",
            ) from exc

    def _find_bulk_group(
        self, routers: list[Router], name: str
    ) -> AdminBulkPlanGroupResponse:
        group_key = self._bulk_group_key(name)
        return next(
            item
            for item in self.list_bulk_plan_groups(routers)
            if item.group_key == group_key
        )

    @staticmethod
    def _bulk_group_key(name: str) -> str:
        normalized_name = name.strip().casefold()
        return uuid.uuid5(uuid.NAMESPACE_URL, f"vlad-wifi:plan-group:{normalized_name}").hex

    def _save_plan_group(
        self,
        group: PlanGroup,
        profile_names: list[str],
        admin: AdminUser,
        action: str,
        ip_address: str | None,
    ) -> None:
        try:
            self._session.flush()
            assigned_profile_names = self._assign_group_profiles(group, profile_names)
            self._session.add(
                AuditLog(
                    actor_type=AuditActorType.ADMIN,
                    admin_user_id=admin.id,
                    action=action,
                    entity_type="plan_group",
                    entity_id=str(group.id),
                    details={
                        "router_id": group.router_id,
                        "name": group.name,
                        "display_order": group.display_order,
                        "sort_by_price": group.sort_by_price,
                        "profile_names": assigned_profile_names,
                    },
                    ip_address=(ip_address or "")[:64] or None,
                )
            )
            self._session.commit()
        except ServiceError:
            self._session.rollback()
            raise
        except IntegrityError as exc:
            self._session.rollback()
            raise ServiceError(
                status.HTTP_409_CONFLICT,
                "A plan group with this name already exists for the hostel.",
            ) from exc

    def _assign_group_profiles(self, group: PlanGroup, profile_names: list[str]) -> list[str]:
        mappings = self._session.scalars(
            select(RouterPackageProfile)
            .options(joinedload(RouterPackageProfile.package))
            .where(RouterPackageProfile.router_id == group.router_id)
        ).all()
        published_by_name = {
            mapping.mikrotik_profile.casefold(): mapping
            for mapping in mappings
            if mapping.is_active and mapping.package.is_active
        }
        selected_keys = {name.casefold() for name in profile_names}
        unavailable = sorted(
            name for name in profile_names if name.casefold() not in published_by_name
        )
        if unavailable:
            raise ServiceError(
                status.HTTP_400_BAD_REQUEST,
                "Only published plans from this hostel can be added to a group.",
            )
        for mapping in mappings:
            key = mapping.mikrotik_profile.casefold()
            if mapping.group_id == group.id and key not in selected_keys:
                mapping.group = None
            elif key in selected_keys:
                mapping.group = group
        self._session.flush()
        return sorted(
            (published_by_name[key].mikrotik_profile for key in selected_keys),
            key=str.casefold,
        )

    @staticmethod
    def _plan_group_response(
        group: PlanGroup, profile_names: list[str]
    ) -> AdminPlanGroupResponse:
        return AdminPlanGroupResponse(
            id=group.id,
            name=group.name,
            description=group.description,
            display_order=group.display_order,
            sort_by_price=group.sort_by_price,
            profile_names=sorted(profile_names, key=str.casefold),
            plan_count=len(profile_names),
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
