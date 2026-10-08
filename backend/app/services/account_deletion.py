from __future__ import annotations

from typing import Protocol

from fastapi import status
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ServiceError
from app.core.security import PinHasher
from app.models.activation import Activation
from app.models.activation_attempt import ActivationAttempt
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.customer_session import CustomerSession
from app.models.email_otp_challenge import EmailOtpChallenge
from app.models.payment_event import PaymentEvent
from app.models.subscription import Subscription
from app.models.support_issue import SupportIssue
from app.models.transaction import Transaction


class AccountDeletionRouterClient(Protocol):
    def delete_hotspot_user(self, username: str) -> bool: ...


class AccountDeletionService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def delete_with_pin(
        self,
        customer: Customer,
        pin: str,
        pin_hasher: PinHasher,
        router_client: AccountDeletionRouterClient,
    ) -> None:
        if not pin_hasher.verify(customer.pin_hash, pin):
            raise ServiceError(status.HTTP_401_UNAUTHORIZED, "The PIN is incorrect.")
        self.erase(customer, router_client)

    def erase(
        self,
        customer: Customer,
        router_client: AccountDeletionRouterClient,
    ) -> None:
        # RouterOS is erased first. If it is unreachable, keep the database account
        # so the customer or retention worker can safely retry later.
        try:
            router_deleted = router_client.delete_hotspot_user(customer.username)
        except Exception as exc:  # RouterOS client exceptions are not stable.
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "The network account could not be deleted. Please try again.",
            ) from exc
        if not router_deleted:
            raise ServiceError(
                status.HTTP_502_BAD_GATEWAY,
                "The network account could not be deleted. Please try again.",
            )

        try:
            self._erase_database_records(customer)
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            # A retry is safe: delete_hotspot_user treats an already-missing user
            # as success and then completes the local erasure.
            raise ServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "The account could not be deleted. Please try again.",
            ) from exc

    def _erase_database_records(self, customer: Customer) -> None:
        customer_id = customer.id
        transaction_rows = self._session.execute(
            select(Transaction.id, Transaction.paystack_reference).where(
                Transaction.customer_id == customer_id
            )
        ).all()
        transaction_ids = [row.id for row in transaction_rows]
        references = [row.paystack_reference for row in transaction_rows]
        activation_ids = list(
            self._session.scalars(
                select(Activation.id).where(Activation.customer_id == customer_id)
            )
        )
        subscription_ids = list(
            self._session.scalars(
                select(Subscription.id).where(Subscription.customer_id == customer_id)
            )
        )

        if subscription_ids:
            self._session.execute(
                update(Subscription)
                .where(Subscription.superseded_by_id.in_(subscription_ids))
                .values(superseded_by_id=None)
            )
        if activation_ids:
            self._session.execute(
                update(Activation)
                .where(Activation.superseded_by_id.in_(activation_ids))
                .values(superseded_by_id=None)
            )

        self._session.execute(delete(Subscription).where(Subscription.customer_id == customer_id))
        if activation_ids:
            self._session.execute(
                delete(ActivationAttempt).where(
                    ActivationAttempt.activation_id.in_(activation_ids)
                )
            )
        self._session.execute(delete(Activation).where(Activation.customer_id == customer_id))
        if transaction_ids or references:
            event_filters = []
            if transaction_ids:
                event_filters.append(PaymentEvent.transaction_id.in_(transaction_ids))
            if references:
                event_filters.append(PaymentEvent.paystack_reference.in_(references))
            self._session.execute(delete(PaymentEvent).where(or_(*event_filters)))
        self._session.execute(delete(Transaction).where(Transaction.customer_id == customer_id))
        self._session.execute(
            delete(EmailOtpChallenge).where(
                or_(
                    EmailOtpChallenge.customer_id == customer_id,
                    EmailOtpChallenge.email == customer.email,
                )
            )
        )
        self._session.execute(delete(AuditLog).where(AuditLog.customer_id == customer_id))
        self._session.execute(
            delete(CustomerSession).where(CustomerSession.customer_id == customer_id)
        )
        self._session.execute(delete(SupportIssue).where(SupportIssue.customer_id == customer_id))
        self._session.execute(delete(Customer).where(Customer.id == customer_id))
