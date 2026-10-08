"""Failure injection uses isolated databases/fake routers, never deployment configuration."""

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from test_hostel_transfer import (
    TEST_CIPHER,
    FakeSession,
    FakeTransferClient,
    _customer,
    _move,
    _user,
)

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.transfer_security import TransferSnapshotCipher
from app.integrations.mikrotik.transfer import guarded_script, mutate_transfer_user
from app.models.activation import Activation
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import ActivationStatus, SubscriptionStatus
from app.models.hostel_transfer import HostelTransferOperation
from app.models.package import Package
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services.account_deletion import AccountDeletionService
from app.services.hostel_transfer_reconciliation import reconcile_hostel_transfers
from app.services.hostel_transfer_recovery import HostelTransferRecovery
from app.services.transfer_lock import transfer_lock


class ProcessStopped(BaseException):
    pass


@pytest.fixture
def transfer():
    session = FakeSession(_customer())
    source = FakeTransferClient(
        _user(
            comment="activation=ACT-original;login=2026-10-01T12:34:56Z",
            **{
                "limit-bytes-total": "1000",
                "bytes-in": "250",
                "bytes-out": "150",
                "limit-uptime": "2h",
                "uptime": "30m",
            },
        )
    )
    destination = FakeTransferClient()
    yield session, source, destination
    engine = session.get_bind()
    session.close()
    engine.dispose()


def operation(session):
    return session.scalar(select(HostelTransferOperation).execution_options(populate_existing=True))


def recover_in_new_session(session, source, destination):
    # Throw away all in-memory operation/customer state as a restart would.
    engine = session.get_bind()
    session.rollback()
    with Session(engine, expire_on_commit=False) as fresh:
        op = operation(fresh)
        with transfer_lock(fresh, op.customer_id):
            HostelTransferRecovery(fresh, TEST_CIPHER).run(
                op, source, destination, raise_errors=False
            )
        return op


def assert_completed(session, source, destination, op):
    assert op.status == "completed" and not op.is_active
    assert op.encrypted_snapshot is None
    assert source.user is None
    assert destination.user["disabled"] == "no"
    assert destination.user["limit-bytes-total"] == "600"
    assert destination.user["limit-uptime"] == "5400s"
    assert destination.user["comment"] == "activation=ACT-original;login=2026-10-01T12:34:56Z"
    with Session(session.get_bind()) as fresh:
        assert fresh.get(Customer, op.customer_id).router_id == "new-hostel"
        assert len(list(fresh.scalars(select(AuditLog)))) == 1


STAGES = [
    "prepared",
    "claiming_source",
    "settling_usage",
    "settled",
    "creating_destination",
    "destination_verified",
    "removing_source",
    "source_removed",
    "committing_database",
    "enabling_destination",
]


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("after_commit", [False, True])
def test_restart_at_each_durable_checkpoint(transfer, monkeypatch, stage, after_commit):
    session, source, destination = transfer
    checkpoint = HostelTransferRecovery._checkpoint
    fired = False

    def interrupt(self, op, current_stage, **kwargs):
        nonlocal fired
        if current_stage == stage and not fired:
            fired = True
            if after_commit:
                checkpoint(self, op, current_stage, **kwargs)
            raise ProcessStopped()
        return checkpoint(self, op, current_stage, **kwargs)

    monkeypatch.setattr(HostelTransferRecovery, "_checkpoint", interrupt)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    assert fired
    monkeypatch.setattr(HostelTransferRecovery, "_checkpoint", checkpoint)
    op = recover_in_new_session(session, source, destination)
    assert_completed(session, source, destination, op)
    # A repeated pass makes no router writes and never recalculates allowance.
    before = source.events[:], destination.events[:]
    op = recover_in_new_session(session, source, destination)
    assert (source.events, destination.events) == before
    assert op.remaining_byte_limits["limit-bytes-total"] == 600
    assert destination.events.count("create-copy") == 1


@pytest.mark.parametrize("action", ["claim", "settle", "create", "remove", "enable"])
def test_process_dies_after_router_write_before_response(transfer, monkeypatch, action):
    session, source, destination = transfer
    client = destination if action in {"create", "enable"} else source
    method_name = (
        "create_hotspot_user_copy"
        if action == "create"
        else "settle_hotspot_transfer_user"
        if action == "settle"
        else "mutate_hotspot_transfer_user"
    )
    original = getattr(client, method_name)

    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs)
        if action != "remove" or kwargs.get("remove"):
            raise ProcessStopped()
        return result

    monkeypatch.setattr(client, method_name, interrupted)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    monkeypatch.setattr(client, method_name, original)
    assert_completed(
        session, source, destination, recover_in_new_session(session, source, destination)
    )


@pytest.mark.parametrize("created", [False, True])
def test_destination_creation_timeout_rolls_back_without_resetting_source(
    transfer, monkeypatch, created
):
    session, source, destination = transfer
    create = destination.create_hotspot_user_copy

    def timeout(*args, **kwargs):
        if created:
            create(*args, **kwargs)
        raise TimeoutError("secret must never appear in logs")

    monkeypatch.setattr(destination, "create_hotspot_user_copy", timeout)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    assert source.user["disabled"] == "yes"
    monkeypatch.setattr(destination, "create_hotspot_user_copy", create)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "rolled_back" and not op.is_active
    assert source.user["disabled"] == "no"
    assert source.user["limit-bytes-total"] == "1000"
    assert source.user["bytes-in"] == "250" and source.user["bytes-out"] == "150"
    assert source.user["uptime"] == "30m"
    assert destination.user is None


@pytest.mark.parametrize("removed", [False, True])
def test_source_removal_timeout_is_resolved_from_observation(transfer, monkeypatch, removed):
    session, source, destination = transfer
    mutate = source.mutate_hotspot_transfer_user

    def timeout(expected, **kwargs):
        if kwargs.get("remove"):
            if removed:
                mutate(expected, **kwargs)
            raise TimeoutError()
        return mutate(expected, **kwargs)

    monkeypatch.setattr(source, "mutate_hotspot_transfer_user", timeout)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    monkeypatch.setattr(source, "mutate_hotspot_transfer_user", mutate)
    op = recover_in_new_session(session, source, destination)
    if removed:
        assert_completed(session, source, destination, op)
    else:
        assert op.status == "rolled_back"
        assert source.user["disabled"] == "no" and source.user["bytes-in"] == "250"
        assert destination.user is None


@pytest.mark.parametrize("commit_reached_database", [False, True])
def test_database_commit_failure_after_source_removal_recovers(
    transfer, monkeypatch, commit_reached_database
):
    session, source, destination = transfer
    commit = session.commit
    fired = False

    def failing_commit():
        nonlocal fired
        op = next(
            (
                value
                for value in session.identity_map.values()
                if isinstance(value, HostelTransferOperation)
            ),
            None,
        )
        if op is not None and op.stage == "database_committed" and not fired:
            fired = True
            if commit_reached_database:
                commit()
            raise SQLAlchemyError("lost commit acknowledgement")
        commit()

    monkeypatch.setattr(session, "commit", failing_commit)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    assert fired and source.user is None
    assert destination.user["disabled"] == "yes"
    monkeypatch.setattr(session, "commit", commit)
    assert_completed(
        session, source, destination, recover_in_new_session(session, source, destination)
    )


def test_database_remains_down_after_source_removal_journal_survives(transfer, monkeypatch):
    session, source, destination = transfer
    commit = session.commit

    def unavailable():
        if source.user is None:
            raise SQLAlchemyError("database is offline")
        commit()

    monkeypatch.setattr(session, "commit", unavailable)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    assert source.user is None and destination.user["disabled"] == "yes"
    # The previously committed removal intent and snapshot survive even though
    # recording the error itself could not commit.
    monkeypatch.setattr(session, "commit", commit)
    op = operation(session)
    assert op.is_active and op.stage == "removing_source" and op.encrypted_snapshot
    assert_completed(
        session, source, destination, recover_in_new_session(session, source, destination)
    )


def pause_after_creation(transfer, monkeypatch):
    session, source, destination = transfer
    create = destination.create_hotspot_user_copy

    def pause(*args, **kwargs):
        create(*args, **kwargs)
        raise ProcessStopped()

    monkeypatch.setattr(destination, "create_hotspot_user_copy", pause)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    monkeypatch.setattr(destination, "create_hotspot_user_copy", create)


@pytest.mark.parametrize("router", ["source", "destination"])
def test_router_unreachable_during_recovery_does_not_delete_any_copy(transfer, monkeypatch, router):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    client = source if router == "source" else destination
    read = client.get_hotspot_user

    def unavailable(_username):
        raise TimeoutError()

    monkeypatch.setattr(client, "get_hotspot_user", unavailable)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "reconciliation_required"
    assert source.user is not None and destination.user is not None
    assert "delete-user" not in source.events and "delete-user" not in destination.events
    monkeypatch.setattr(client, "get_hotspot_user", read)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "rolled_back"


@pytest.mark.parametrize(
    "router,field,value",
    [
        ("source", "id", "*99"),
        ("source", "password", "changed"),
        ("destination", "comment", "unrelated"),
        ("destination", "profile", "new-plan"),
        ("destination", "bytes-in", "1"),
        ("destination", "disabled", "no"),
    ],
)
def test_changed_accounts_require_review_without_destructive_cleanup(
    transfer, monkeypatch, router, field, value
):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    client = source if router == "source" else destination
    client.user[field] = value
    op = recover_in_new_session(session, source, destination)
    assert op.status == "manual_review" and op.is_active and op.encrypted_snapshot
    assert "delete-user" not in source.events and "delete-user" not in destination.events
    assert client.user[field] == value


@pytest.mark.parametrize("router", ["source", "destination"])
def test_rollback_interrupted_by_router_outage_retries_safely(transfer, monkeypatch, router):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    HostelTransferRecovery(session, TEST_CIPHER).record_failure(
        operation(session).id, "router_timeout", rollback=True
    )
    client = source if router == "source" else destination
    mutate = client.mutate_hotspot_transfer_user

    def unavailable(*_args, **_kwargs):
        raise TimeoutError()

    monkeypatch.setattr(client, "mutate_hotspot_transfer_user", unavailable)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "reconciliation_required" and op.encrypted_snapshot
    assert source.user is not None and source.user["disabled"] == "yes"
    monkeypatch.setattr(client, "mutate_hotspot_transfer_user", mutate)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "rolled_back"
    assert source.user["disabled"] == "no" and source.user["bytes-in"] == "250"
    assert destination.user is None


@pytest.mark.parametrize("kind", ["bytes", "uptime"])
def test_exhausted_allowance_stays_disabled_after_restart(transfer, monkeypatch, kind):
    session, source, destination = transfer
    if kind == "bytes":
        source.user["limit-bytes-total"] = "400"
    else:
        source.user["limit-uptime"] = "30m"
    pause_after_creation(transfer, monkeypatch)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "completed"
    assert destination.user["disabled"] == "yes"
    if kind == "bytes":
        assert destination.user["limit-bytes-total"] == "1"
        assert op.remaining_byte_limits["limit-bytes-total"] == 0
    else:
        assert destination.user["limit-uptime"] == "1s"
        assert op.remaining_uptime_seconds == 0


@pytest.mark.parametrize("action", ["remove_destination", "restore_source"])
def test_crash_after_rollback_router_write_is_idempotent(transfer, monkeypatch, action):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    HostelTransferRecovery(session, TEST_CIPHER).record_failure(
        operation(session).id, "router_timeout", rollback=True
    )
    client = destination if action == "remove_destination" else source
    mutate = client.mutate_hotspot_transfer_user

    def interrupted(*args, **kwargs):
        mutate(*args, **kwargs)
        raise ProcessStopped()

    monkeypatch.setattr(client, "mutate_hotspot_transfer_user", interrupted)
    with pytest.raises(ProcessStopped):
        recover_in_new_session(session, source, destination)
    monkeypatch.setattr(client, "mutate_hotspot_transfer_user", mutate)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "rolled_back" and not op.is_active
    assert source.user["disabled"] == "no" and source.user["bytes-in"] == "250"
    assert destination.user is None


@pytest.mark.parametrize("after_commit", [False, True])
def test_lost_terminal_commit_response_recovers_without_router_writes(
    transfer, monkeypatch, after_commit
):
    session, source, destination = transfer
    commit = session.commit

    def interrupted():
        op = next(
            (
                value
                for value in session.identity_map.values()
                if isinstance(value, HostelTransferOperation)
            ),
            None,
        )
        if op is not None and op.status == "completed":
            if after_commit:
                commit()
            raise ProcessStopped()
        commit()

    monkeypatch.setattr(session, "commit", interrupted)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    monkeypatch.setattr(session, "commit", commit)
    events = source.events[:], destination.events[:]
    op = recover_in_new_session(session, source, destination)
    assert_completed(session, source, destination, op)
    assert source.events.count("delete-user") == events[0].count("delete-user")
    assert destination.events.count("create-copy") == 1
    assert destination.events.count("mutate-user") == events[1].count("mutate-user")


@pytest.mark.parametrize("crash", [False, True])
def test_first_login_after_enabling_is_preserved(transfer, monkeypatch, crash):
    session, source, destination = transfer
    source.user["comment"] = "activation=ACT-never-used"
    mutate = destination.mutate_hotspot_transfer_user

    def login(*args, **kwargs):
        result = mutate(*args, **kwargs)
        destination.user["comment"] += ";login=2026-10-08 12:00:00"
        if crash:
            raise ProcessStopped()
        return {**result, "comment": destination.user["comment"]}

    monkeypatch.setattr(destination, "mutate_hotspot_transfer_user", login)
    if crash:
        with pytest.raises(ProcessStopped):
            _move(source, destination, session)
        monkeypatch.setattr(destination, "mutate_hotspot_transfer_user", mutate)
        assert recover_in_new_session(session, source, destination).status == "completed"
    else:
        _move(source, destination, session)
    assert destination.user["comment"] == "activation=ACT-never-used;login=2026-10-08 12:00:00"


def test_usage_changes_after_settlement_require_review(transfer, monkeypatch):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    source.user["bytes-in"] = "300"
    op = recover_in_new_session(session, source, destination)
    assert op.status == "manual_review" and op.error_code == "source_usage_changed_after_settlement"
    assert source.user is not None and destination.user["disabled"] == "yes"
    assert "delete-user" not in source.events and "delete-user" not in destination.events


@pytest.mark.parametrize("stage", STAGES)
def test_database_checkpoint_failure_stops_then_recovers(transfer, monkeypatch, stage):
    session, source, destination = transfer
    checkpoint = HostelTransferRecovery._checkpoint
    fired = False

    def fail_once(self, op, current_stage, **kwargs):
        nonlocal fired
        if current_stage == stage and not fired:
            fired = True
            raise SQLAlchemyError("temporary database failure")
        checkpoint(self, op, current_stage, **kwargs)

    monkeypatch.setattr(HostelTransferRecovery, "_checkpoint", fail_once)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    monkeypatch.setattr(HostelTransferRecovery, "_checkpoint", checkpoint)
    assert fired
    assert_completed(
        session, source, destination, recover_in_new_session(session, source, destination)
    )


def test_missing_only_remaining_copy_requires_review(transfer, monkeypatch):
    session, source, destination = transfer
    remove = source.mutate_hotspot_transfer_user

    def interrupt(expected, **kwargs):
        result = remove(expected, **kwargs)
        if kwargs.get("remove"):
            raise ProcessStopped()
        return result

    monkeypatch.setattr(source, "mutate_hotspot_transfer_user", interrupt)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    destination.user = None
    monkeypatch.setattr(source, "mutate_hotspot_transfer_user", remove)
    op = recover_in_new_session(session, source, destination)
    assert op.status == "manual_review"
    assert op.error_code == "destination_missing_after_source_removal"
    assert op.encrypted_snapshot and op.remaining_byte_limits["limit-bytes-total"] == 600
    assert destination.events.count("create-copy") == 1


def test_transport_error_does_not_override_manual_review(transfer, monkeypatch):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    destination.user["profile"] = "changed"
    op = recover_in_new_session(session, source, destination)
    assert op.status == "manual_review"
    error_code = op.error_code
    HostelTransferRecovery(session, TEST_CIPHER).record_failure(op.id, "router_unavailable")
    op = operation(session)
    assert op.status == "manual_review" and op.error_code == error_code


def test_new_request_after_rollback_uses_current_usage(transfer, monkeypatch):
    session, source, destination = transfer
    create = destination.create_hotspot_user_copy

    def lost_response(*args, **kwargs):
        create(*args, **kwargs)
        raise TimeoutError()

    monkeypatch.setattr(destination, "create_hotspot_user_copy", lost_response)
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    monkeypatch.setattr(destination, "create_hotspot_user_copy", create)
    assert recover_in_new_session(session, source, destination).status == "rolled_back"
    source.user["bytes-in"] = "350"
    source.user["uptime"] = "45m"
    result = _move(source, destination, session)
    assert result.remaining_data_limit_bytes == 500
    assert destination.user["limit-bytes-total"] == "500"
    assert destination.user["limit-uptime"] == "4500s"
    assert destination.user["comment"] == "activation=ACT-original;login=2026-10-01T12:34:56Z"
    assert len(list(session.scalars(select(HostelTransferOperation)))) == 2


def test_deletion_refuses_a_router_resolved_before_transfer_finished(transfer):
    session, source, _destination = transfer
    customer_id = session.customer.id
    with Session(session.get_bind()) as other:
        other.get(Customer, customer_id).router_id = "new-hostel"
        other.commit()
    with pytest.raises(ServiceError):
        AccountDeletionService(session).erase(session.customer, source)
    assert source.user is not None and "delete-user" not in source.events


def test_pending_transfer_prevents_another_transfer_or_account_erasure(transfer, monkeypatch):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    before = source.events[:], destination.events[:]
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == "hostel_transfer_in_progress"
    with pytest.raises(ServiceError):
        AccountDeletionService(session).erase(session.customer, source)
    assert (source.events, destination.events) == before
    assert len(list(session.scalars(select(HostelTransferOperation)))) == 1


def test_concurrent_requests_are_rejected_across_checkpoint_commits(transfer):
    session, _source, _destination = transfer
    with Session(session.get_bind()) as other:
        with transfer_lock(session, session.customer.id):
            session.commit()
            with pytest.raises(ServiceError) as error, transfer_lock(other, session.customer.id):
                pytest.fail("Second lock must not be acquired")
            assert error.value.status_code == 409
        # Crash/normal return releases the lock for the next recovery worker.
        with transfer_lock(other, session.customer.id):
            pass


def test_database_unique_active_operation_is_a_second_concurrency_barrier(transfer, monkeypatch):
    pause_after_creation(transfer, monkeypatch)
    session, _source, _destination = transfer
    existing = operation(session)
    duplicate = HostelTransferOperation(
        id=uuid.uuid4(),
        customer_id=existing.customer_id,
        username=existing.username,
        source_router_id=existing.source_router_id,
        destination_router_id=existing.destination_router_id,
        destination_router_name=existing.destination_router_name,
        source_user_id=existing.source_user_id,
        encrypted_snapshot=existing.encrypted_snapshot,
        actor_type="customer",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_automatic_reconciliation_honors_backoff_and_manual_review(transfer, monkeypatch):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    op = operation(session)
    settings = Settings(
        _env_file=None, pin_hash_secret="test-transfer-secret-with-at-least-32-characters"
    )
    factory = sessionmaker(session.get_bind(), expire_on_commit=False)

    @contextmanager
    def clients(router):
        yield source if router.router_id == "old-hostel" else destination

    def reconcile(**kwargs):
        return reconcile_hostel_transfers(
            settings, session_factory=factory, client_context=clients, **kwargs
        )

    op.next_retry_at = datetime.now(UTC) + timedelta(hours=1)
    session.commit()
    before = source.events[:], destination.events[:]
    assert reconcile() == 0
    op.status = "manual_review"
    op.next_retry_at = None
    session.commit()
    assert reconcile() == 0
    assert (source.events, destination.events) == before
    assert reconcile(operation_id=op.id, retry_manual=True) == 1
    assert_completed(session, source, destination, operation(session))


def add_subscription(session):
    customer = session.customer
    package = Package(code="test", name="Test", amount=1, duration_seconds=604800)
    session.add(package)
    session.flush()
    transaction = Transaction(
        customer_id=customer.id,
        package_id=package.id,
        router_id=customer.router_id,
        paystack_reference="test-payment",
        amount=1,
    )
    session.add(transaction)
    session.flush()
    activation = Activation(
        transaction_id=transaction.id,
        customer_id=customer.id,
        package_id=package.id,
        router_id=customer.router_id,
        target_profile="paid",
        status=ActivationStatus.SUCCESS,
        sequence_number=1,
    )
    session.add(activation)
    session.flush()
    starts = datetime(2026, 10, 1, 12, 34, 56, tzinfo=UTC)
    subscription = Subscription(
        customer_id=customer.id,
        package_id=package.id,
        transaction_id=transaction.id,
        activation_id=activation.id,
        router_id=customer.router_id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=starts,
        expires_at=starts + timedelta(days=7),
    )
    session.add(subscription)
    session.commit()
    return subscription


def test_recovery_preserves_subscription_dates_and_related_records(transfer, monkeypatch):
    session, source, destination = transfer
    subscription = add_subscription(session)
    starts, expires = subscription.starts_at, subscription.expires_at
    pause_after_creation(transfer, monkeypatch)
    op = recover_in_new_session(session, source, destination)
    assert_completed(session, source, destination, op)
    session.refresh(subscription)
    assert subscription.router_id == "new-hostel"
    assert subscription.starts_at.replace(tzinfo=UTC) == starts
    assert subscription.expires_at.replace(tzinfo=UTC) == expires
    assert subscription.activation.router_id == "old-hostel"
    assert subscription.transaction.router_id == "old-hostel"


def test_snapshots_are_authenticated_bound_to_operation_and_cleared(transfer, monkeypatch, caplog):
    pause_after_creation(transfer, monkeypatch)
    session, source, destination = transfer
    op = operation(session)
    assert "123456" not in op.encrypted_snapshot
    assert "123456" not in json.dumps(op.last_confirmed_state)
    with pytest.raises(InvalidToken):
        TEST_CIPHER.decrypt(uuid.uuid4(), op.encrypted_snapshot)
    wrong_key = TransferSnapshotCipher("a-different-secret-with-at-least-32-characters")
    with pytest.raises(InvalidToken):
        wrong_key.decrypt(op.id, op.encrypted_snapshot)
    op.encrypted_snapshot = op.encrypted_snapshot[:-10] + "tampered"
    session.commit()
    op = recover_in_new_session(session, source, destination)
    assert op.status == "manual_review" and op.error_code == "snapshot_invalid"
    assert "123456" not in caplog.text
    assert "delete-user" not in source.events and "delete-user" not in destination.events


def test_conditional_script_escapes_all_untrusted_data_and_checks_identity():
    expected = {
        "id": "*A",
        "name": 'user"; :error "injected',
        "password": "$secret",
        "profile": "paid",
        "comment": "login=original",
        "disabled": "yes",
    }
    script = guarded_script(expected, remove=True)
    assert "injected" not in script and "$secret" not in script
    assert "get $transferId name" in script and "get $transferId password" in script
    assert "get $transferId comment" in script and "get $transferId disabled" in script
    assert "/ip hotspot user remove $transferId" in script
    with pytest.raises(ValueError):
        guarded_script({**expected, "id": '*A; :error "injected'}, remove=True)


def test_conditional_mutations_use_synchronous_execute_and_confirm_removal():
    calls = []

    class Resource:
        def call(self, command, args):
            calls.append((command, args))

    class Client:
        def connect(self):
            return self

        def get_resource(self, path):
            assert path == "/"
            return Resource()

        def get_hotspot_user(self, _username):
            return None

    assert mutate_transfer_user(Client(), {"id": "*1", "name": "ama"}, remove=True) is None
    assert calls[0][0] == "execute" and calls[0][1]["as-string"] == ""
