"""Unpaid checkouts must not trap customers, or activate on a router they have left."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_hostel_transfer import FakeSession, FakeTransferClient, _customer, _move, _user

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.integrations.paystack import InitializedTransaction, VerifiedTransaction
from app.models.customer import Customer
from app.models.enums import ActivationStatus, ActivationTrigger, PaymentStatus, SubscriptionStatus
from app.models.hostel_transfer import HostelTransferOperation
from app.models.package import Package, RouterPackageProfile
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services.payment_verification import PaymentVerificationService
from app.services.transfer_lock import transfer_lock


class CheckoutGateway:
    def initialize_transaction(self, **arguments):
        self.arguments = arguments
        return InitializedTransaction(
            authorization_url="https://checkout.paystack.com/test",
            access_code="test",
            reference=arguments["reference"],
        )

    def verify_transaction(self, reference):
        return VerifiedTransaction(
            reference=reference,
            status="success",
            amount=self.arguments["amount"],
            currency=self.arguments["currency"],
            paid_at=datetime.now(UTC),
            customer_email=self.arguments["email"],
            metadata=self.arguments["metadata"],
        )


class CheckoutRouter(FakeTransferClient):
    def __init__(self, user=None):
        super().__init__(user)
        self.activations = []

    def disconnect(self):
        pass

    def activate_hotspot_user(self, *, username, profile, comment, data_limit_bytes):
        assert self.user is not None and self.user["name"] == username
        self.activations.append(comment)
        self.user.update(
            profile=profile,
            comment=comment,
            disabled="no",
            **{"limit-bytes-total": str(data_limit_bytes or 0)},
        )
        return dict(self.user)


@pytest.fixture
def checkout(monkeypatch):
    session = FakeSession(_customer())
    source = CheckoutRouter(
        _user(comment="login=2026-10-01T12:34:56Z", **{"limit-bytes-total": "1000", "bytes-in": "400"})
    )
    destination = CheckoutRouter()
    package = Package(code="weekly", name="Weekly", amount=Decimal("10.00"), data_limit_bytes=2000)
    session.add(package)
    session.flush()
    session.add(RouterPackageProfile(
        router_id="old-hostel", package_id=package.id, mikrotik_profile="paid", is_active=True,
    ))
    session.commit()
    gateway = CheckoutGateway()
    clients_used = []

    def client_for(router_id):
        clients_used.append(router_id)
        return source if router_id == "old-hostel" else destination

    service = PaymentVerificationService(
        session, Settings(paystack_callback_url="https://wifi.example/callback"), gateway, client_for,
    )
    monkeypatch.setattr(service._activation_service, "_notify_activation", lambda *_a, **_k: None)
    result = service.initialize(session.customer, package.id)
    transaction = session.scalar(select(Transaction).where(Transaction.paystack_reference == result.reference))
    clients_used.clear()
    yield SimpleNamespace(
        session=session, source=source, destination=destination, service=service,
        transaction=transaction, activation=transaction.activation, clients_used=clients_used,
    )
    engine = session.get_bind()
    session.close()
    engine.dispose()


@pytest.mark.parametrize("payment_status", [PaymentStatus.PENDING, PaymentStatus.FAILED])
def test_unpaid_checkout_does_not_block_hostel_transfer(checkout, payment_status):
    checkout.transaction.payment_status = payment_status
    checkout.session.commit()
    result = _move(checkout.source, checkout.destination, checkout.session)
    assert result.router_id == "new-hostel"
    assert result.remaining_data_limit_bytes == 600
    assert checkout.source.user is None
    assert checkout.destination.user["comment"] == "login=2026-10-01T12:34:56Z"
    assert checkout.activation.status == ActivationStatus.NOT_STARTED
    assert checkout.activation.attempt_count == 0
    assert checkout.transaction.payment_status == payment_status
    assert checkout.transaction.router_id == "old-hostel"


@pytest.mark.parametrize("activation_status", [
    ActivationStatus.NOT_STARTED, ActivationStatus.PROCESSING, ActivationStatus.PROVISIONING,
    ActivationStatus.RETRY_REQUIRED, ActivationStatus.RECONCILIATION_REQUIRED,
])
def test_paid_unfinished_activation_still_blocks_transfer(checkout, activation_status):
    checkout.transaction.payment_status = PaymentStatus.SUCCESS
    checkout.activation.status = activation_status
    checkout.session.commit()
    before = dict(checkout.source.user)
    with pytest.raises(ServiceError) as error:
        _move(checkout.source, checkout.destination, checkout.session)
    assert error.value.error_code == "hostel_activation_pending"
    assert checkout.source.user == before
    assert "clear-auth" not in checkout.source.events
    assert checkout.destination.user is None
    assert checkout.session.scalar(select(HostelTransferOperation.id)) is None


@pytest.mark.parametrize("activation_status,attempt_count", [
    (ActivationStatus.NOT_STARTED, 1), (ActivationStatus.PROCESSING, 1),
    (ActivationStatus.PROVISIONING, 1), (ActivationStatus.RETRY_REQUIRED, 1),
    (ActivationStatus.RECONCILIATION_REQUIRED, 1),
])
def test_unpaid_activation_with_possible_router_writes_still_blocks(checkout, activation_status, attempt_count):
    checkout.activation.status = activation_status
    checkout.activation.attempt_count = attempt_count
    checkout.session.commit()
    with pytest.raises(ServiceError) as error:
        _move(checkout.source, checkout.destination, checkout.session)
    assert error.value.error_code == "hostel_activation_pending"
    assert checkout.source.user is not None
    assert checkout.destination.user is None


@pytest.mark.parametrize("payment_status", [PaymentStatus.PENDING, PaymentStatus.FAILED])
@pytest.mark.parametrize("separate_session", [False, True])
def test_checkout_paid_after_move_activates_once_at_current_hostel(checkout, payment_status, separate_session):
    checkout.transaction.payment_status = payment_status
    checkout.session.commit()
    if separate_session:
        with Session(checkout.session.get_bind(), expire_on_commit=False) as moving_session:
            moving_session.customer = moving_session.get(Customer, checkout.session.customer.id)
            _move(checkout.source, checkout.destination, moving_session)
        # The payment worker still has a customer cached at the old hostel.
        assert checkout.session.customer.router_id == "old-hostel"
    else:
        _move(checkout.source, checkout.destination, checkout.session)
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
    )
    assert result.payment_status == PaymentStatus.SUCCESS
    assert result.activation_status == ActivationStatus.SUCCESS
    assert checkout.clients_used == ["new-hostel"]
    assert checkout.activation.router_id == "new-hostel"
    assert checkout.transaction.router_id == "old-hostel"
    assert checkout.transaction.amount == 10
    assert checkout.source.user is None
    assert len(checkout.destination.activations) == 1
    assert checkout.destination.user["limit-bytes-total"] == "2000"
    subscription = checkout.session.scalar(select(Subscription))
    assert subscription.router_id == "new-hostel"
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.starts_at is None and subscription.expires_at is None
    checkout.service.verify(checkout.transaction.paystack_reference, trigger=ActivationTrigger.CUSTOMER_RETRY)
    assert len(checkout.destination.activations) == 1
    assert checkout.session.scalars(select(Subscription)).all() == [subscription]


@pytest.mark.parametrize("stage", ["source_freezing", "source_removed"])
def test_payment_confirmed_during_move_is_deferred_then_activates_at_destination(checkout, stage):
    original = checkout.source.mutate_hotspot_transfer_user
    verified = []

    def mutate(expected, **options):
        result = original(expected, **options)
        if not verified and bool(options.get("remove")) == (stage == "source_removed"):
            verified.append(checkout.service.verify(
                checkout.transaction.paystack_reference, trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
            ))
            assert verified[0].payment_status == PaymentStatus.SUCCESS
            assert verified[0].activation_status == ActivationStatus.NOT_STARTED
            assert checkout.clients_used == []
        return result

    checkout.source.mutate_hotspot_transfer_user = mutate
    _move(checkout.source, checkout.destination, checkout.session)
    assert len(verified) == 1
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.CUSTOMER_RETRY,
    )
    assert result.activation_status == ActivationStatus.SUCCESS
    assert checkout.clients_used == ["new-hostel"]
    assert len(checkout.destination.activations) == 1


def test_active_recovery_journal_defers_payment_without_changing_routers(checkout):
    from test_hostel_transfer import TEST_CIPHER
    from test_hostel_transfer_recovery import ProcessStopped

    from app.services.hostel_transfer_recovery import HostelTransferRecovery

    original = checkout.source.mutate_hotspot_transfer_user

    def stop(expected, **options):
        original(expected, **options)
        raise ProcessStopped()

    checkout.source.mutate_hotspot_transfer_user = stop
    with pytest.raises(ProcessStopped):
        _move(checkout.source, checkout.destination, checkout.session)
    checkout.source.mutate_hotspot_transfer_user = original
    before = dict(checkout.source.user)
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
    )
    assert result.payment_status == PaymentStatus.SUCCESS
    assert result.activation_status == ActivationStatus.NOT_STARTED
    assert checkout.source.user == before
    assert checkout.destination.user is None
    assert checkout.clients_used == []
    operation = checkout.session.scalar(select(HostelTransferOperation))
    assert operation.is_active
    HostelTransferRecovery(checkout.session, TEST_CIPHER).run(operation, checkout.source, checkout.destination)
    assert operation.status == "completed"
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.CUSTOMER_RETRY,
    )
    assert result.activation_status == ActivationStatus.SUCCESS
    assert checkout.clients_used == ["new-hostel"]


def test_activation_lock_prevents_concurrent_move_and_is_released_after_success(checkout):
    checkout.transaction.payment_status = PaymentStatus.SUCCESS
    checkout.session.commit()
    with transfer_lock(checkout.session, checkout.session.customer.id):
        result = checkout.service.verify(
            checkout.transaction.paystack_reference, trigger=ActivationTrigger.CUSTOMER_RETRY,
        )
        assert result.activation_status == ActivationStatus.NOT_STARTED
        assert checkout.clients_used == []
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.CUSTOMER_RETRY,
    )
    assert result.activation_status == ActivationStatus.SUCCESS
    assert checkout.clients_used == ["old-hostel"]
    _move(checkout.source, checkout.destination, checkout.session)
    assert checkout.session.customer.router_id == "new-hostel"
    assert len(checkout.source.activations) == 1


def test_transfer_cannot_interrupt_router_activation(checkout):
    original = checkout.source.activate_hotspot_user
    conflicts = []

    def activate(**options):
        with pytest.raises(ServiceError) as error:
            _move(checkout.source, checkout.destination, checkout.session)
        conflicts.append(error.value.error_code)
        assert checkout.destination.user is None
        return original(**options)

    checkout.source.activate_hotspot_user = activate
    result = checkout.service.verify(
        checkout.transaction.paystack_reference, trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
    )
    assert result.activation_status == ActivationStatus.SUCCESS
    assert conflicts == ["hostel_transfer_in_progress"]
    assert checkout.session.customer.router_id == "old-hostel"
    assert len(checkout.source.activations) == 1
