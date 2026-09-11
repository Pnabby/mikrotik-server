from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.enums import PaymentStatus, SubscriptionStatus
from app.models.package import Package, RouterPackageProfile
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.schemas.account import (
    AvailablePlanResponse,
    CurrentPlanResponse,
    CustomerAccountResponse,
    PreviousPlanResponse,
    PurchaseHistoryResponse,
)


class CustomerAccountService:
    def __init__(self, session: Session, *, payments_enabled: bool = False) -> None:
        self._session = session
        self._payments_enabled = payments_enabled

    def overview(self, customer: Customer) -> CustomerAccountResponse:
        now = datetime.now(UTC)
        current_subscription = self._session.scalar(
            select(Subscription)
            .options(joinedload(Subscription.package))
            .where(
                Subscription.customer_id == customer.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            .order_by(Subscription.starts_at.desc(), Subscription.created_at.desc())
            .limit(1)
        )
        if (
            current_subscription is not None
            and current_subscription.expires_at is not None
            and _as_utc(current_subscription.expires_at) <= now
        ):
            current_subscription = None

        previous_subscriptions = self._session.scalars(
            select(Subscription)
            .options(
                joinedload(Subscription.package),
                joinedload(Subscription.transaction),
            )
            .where(
                Subscription.customer_id == customer.id,
                or_(
                    Subscription.status.in_(
                        {
                            SubscriptionStatus.EXPIRED,
                            SubscriptionStatus.CANCELLED,
                            SubscriptionStatus.SUPERSEDED,
                        }
                    ),
                    and_(
                        Subscription.status == SubscriptionStatus.ACTIVE,
                        Subscription.expires_at.is_not(None),
                        Subscription.expires_at <= now,
                    ),
                ),
            )
            .order_by(Subscription.starts_at.desc(), Subscription.created_at.desc())
            .limit(5)
        ).all()

        plan_mappings = self._session.scalars(
            select(RouterPackageProfile)
            .options(
                joinedload(RouterPackageProfile.package),
                joinedload(RouterPackageProfile.group),
            )
            .join(RouterPackageProfile.package)
            .where(
                RouterPackageProfile.router_id == customer.router_id,
                RouterPackageProfile.is_active.is_(True),
                Package.is_active.is_(True),
            )
            .order_by(Package.is_promotional.desc(), Package.amount, Package.duration_seconds)
        ).all()
        successfully_purchased_package_ids = set(
            self._session.scalars(
                select(Transaction.package_id).where(
                    Transaction.customer_id == customer.id,
                    Transaction.payment_status == PaymentStatus.SUCCESS,
                )
            ).all()
        )
        transactions = self._session.scalars(
            select(Transaction)
            .options(joinedload(Transaction.package), joinedload(Transaction.activation))
            .where(Transaction.customer_id == customer.id)
            .order_by(Transaction.created_at.desc())
            .limit(50)
        ).all()
        relevant_package_ids = {transaction.package_id for transaction in transactions}
        if current_subscription is not None:
            relevant_package_ids.add(current_subscription.package_id)
        relevant_package_ids.update(
            subscription.package_id for subscription in previous_subscriptions
        )
        presentation_mappings = (
            self._session.scalars(
                select(RouterPackageProfile).where(
                    RouterPackageProfile.router_id == customer.router_id,
                    RouterPackageProfile.package_id.in_(relevant_package_ids),
                )
            ).all()
            if relevant_package_ids
            else []
        )
        presentation_by_package = {mapping.package_id: mapping for mapping in presentation_mappings}
        router_name = customer.router.name if customer.router is not None else "Your hostel"
        return CustomerAccountResponse(
            username=customer.username,
            email=customer.email,
            phone_number=customer.phone_number,
            phone_verified=customer.phone_verified_at is not None,
            hostel_name=router_name,
            account_status=customer.account_status,
            current_plan=(
                CurrentPlanResponse(
                    name=_display_name(
                        current_subscription.package,
                        presentation_by_package.get(current_subscription.package_id),
                    ),
                    status=current_subscription.status,
                    starts_at=current_subscription.starts_at,
                    expires_at=current_subscription.expires_at,
                    duration_seconds=current_subscription.package.duration_seconds,
                    data_limit_bytes=current_subscription.package.data_limit_bytes,
                    device_limit=current_subscription.package.device_limit,
                    download_speed=_download_speed(
                        presentation_by_package.get(current_subscription.package_id)
                    ),
                )
                if current_subscription is not None
                else None
            ),
            available_plans=[
                AvailablePlanResponse(
                    id=mapping.package.id,
                    name=_display_name(mapping.package, mapping),
                    description=_display_description(mapping.package, mapping),
                    amount=mapping.package.amount,
                    currency=mapping.package.currency,
                    duration_seconds=mapping.package.duration_seconds,
                    data_limit_bytes=mapping.package.data_limit_bytes,
                    device_limit=mapping.package.device_limit,
                    download_speed=_download_speed(mapping),
                    is_promotional=mapping.package.is_promotional,
                    promo_claimed=(
                        mapping.package.is_promotional
                        and mapping.package.id in successfully_purchased_package_ids
                    ),
                    purchase_available=(
                        (
                            (
                                mapping.package.is_promotional
                                and mapping.package.amount == 0
                            )
                            or (self._payments_enabled and mapping.package.amount > 0)
                        )
                        and not (
                            mapping.package.is_promotional
                            and mapping.package.id in successfully_purchased_package_ids
                        )
                    ),
                    group_id=mapping.group_id,
                    group_name=mapping.group.name if mapping.group else None,
                    group_description=mapping.group.description if mapping.group else None,
                    group_display_order=(mapping.group.display_order if mapping.group else None),
                    group_sort_by_price=(mapping.group.sort_by_price if mapping.group else False),
                )
                for mapping in plan_mappings
            ],
            previous_plans=[
                PreviousPlanResponse(
                    id=subscription.id,
                    name=_display_name(
                        subscription.package,
                        presentation_by_package.get(subscription.package_id),
                    ),
                    status=subscription.status,
                    purchased_at=(
                        subscription.transaction.paid_at or subscription.transaction.created_at
                        if subscription.transaction is not None
                        else subscription.created_at
                    ),
                    starts_at=subscription.starts_at,
                    expires_at=subscription.expires_at,
                    ended_at=subscription.ended_at,
                )
                for subscription in previous_subscriptions
            ],
            purchases=[
                PurchaseHistoryResponse(
                    reference=transaction.paystack_reference,
                    plan_name=_display_name(
                        transaction.package,
                        presentation_by_package.get(transaction.package_id),
                    ),
                    amount=transaction.amount,
                    currency=transaction.currency,
                    status=transaction.payment_status,
                    activation_status=(
                        transaction.activation.status if transaction.activation else None
                    ),
                    purchased_at=transaction.created_at,
                    paid_at=transaction.paid_at,
                )
                for transaction in transactions
            ],
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _display_name(package: Package, mapping: RouterPackageProfile | None) -> str:
    return mapping.display_name if mapping and mapping.display_name else package.name


def _display_description(package: Package, mapping: RouterPackageProfile | None) -> str | None:
    return mapping.description if mapping and mapping.description else package.description


def _download_speed(mapping: RouterPackageProfile | None) -> str | None:
    return mapping.download_speed if mapping else None
