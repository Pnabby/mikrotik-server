"""Optional integration tests: use only a dedicated loopback PostgreSQL instance."""

import multiprocessing
import os
import threading
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from test_hostel_transfer import FakeTransferClient, _customer, _move, _user

from alembic import command
from app.core.exceptions import ServiceError
from app.db.base import Base
from app.services.transfer_lock import transfer_lock


@pytest.fixture
def isolated_postgres():
    raw_url = os.environ.get("HOSTEL_TRANSFER_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip(
            "Set HOSTEL_TRANSFER_TEST_DATABASE_URL for isolated PostgreSQL integration tests."
        )
    url = make_url(raw_url)
    if (
        url.host != "127.0.0.1"
        or url.port != 55439
        or url.database != "hostel_transfer_recovery_test"
    ):
        pytest.fail("Integration tests require the dedicated loopback test database on port 55439.")
    admin_engine = create_engine(url)
    schema = "transfer_test_" + uuid.uuid4().hex
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        yield raw_url, schema, engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def child_try_lock(url, schema, customer_id, output):
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    with Session(engine) as session:
        try:
            with transfer_lock(session, customer_id):
                output.put("acquired")
        except ServiceError as exc:
            output.put(exc.error_code)
    engine.dispose()


def test_activation_respects_transfer_lock_and_uses_current_hostel(isolated_postgres, monkeypatch):
    from test_hostel_transfer_pending_payments import CheckoutRouter

    from app.core.config import Settings
    from app.models.activation import Activation
    from app.models.enums import ActivationStatus, ActivationTrigger, PaymentStatus
    from app.models.package import Package
    from app.models.router import Router
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction
    from app.services.package_activation import PackageActivationService

    _url, _schema, engine = isolated_postgres
    customer = _customer()
    client = CheckoutRouter(_user())
    used = []

    def client_for(router_id):
        used.append(router_id)
        return client

    with Session(engine, expire_on_commit=False) as session:
        session.add_all([
            Router(id="old-hostel", name="Old", vpn_host="old.test"),
            Router(id="new-hostel", name="New", vpn_host="new.test"),
        ])
        package = Package(code="weekly", name="Weekly", amount=10, data_limit_bytes=2000)
        session.add(package)
        session.flush()
        session.add(customer)
        session.flush()
        transaction = Transaction(
            customer_id=customer.id, package_id=package.id, router_id="old-hostel",
            paystack_reference="late-payment", amount=10, payment_status=PaymentStatus.SUCCESS,
        )
        session.add(transaction)
        session.flush()
        activation = Activation(
            customer_id=customer.id, package_id=package.id, transaction_id=transaction.id,
            router_id="old-hostel", target_profile="paid",
        )
        session.add(activation)
        session.commit()
        service = PackageActivationService(session, client_for, Settings())
        monkeypatch.setattr(service, "_notify_activation", lambda *_a, **_k: None)
        with Session(engine) as transferring, transfer_lock(transferring, customer.id):
            assert service.activate(
                activation, trigger=ActivationTrigger.PAYSTACK_WEBHOOK,
            ) == ActivationStatus.NOT_STARTED
            assert used == []
            assert activation.attempt_count == 0
        customer.router_id = "new-hostel"
        session.commit()
        assert service.activate(
            activation, trigger=ActivationTrigger.CUSTOMER_RETRY,
        ) == ActivationStatus.SUCCESS
        assert used == ["new-hostel"]
        assert activation.router_id == "new-hostel"
        assert transaction.router_id == "old-hostel"
        assert session.scalars(select(Subscription)).one().router_id == "new-hostel"


def test_customer_lock_survives_commits_and_blocks_another_process(isolated_postgres):
    url, schema, engine = isolated_postgres
    customer_id = uuid.uuid4()
    context = multiprocessing.get_context("spawn")
    output = context.Queue()
    with Session(engine) as session, transfer_lock(session, customer_id):
        session.commit()
        session.rollback()
        child = context.Process(target=child_try_lock, args=(url, schema, customer_id, output))
        child.start()
        assert output.get(timeout=30) == "hostel_transfer_in_progress"
        child.join(30)
        assert child.exitcode == 0
    with Session(engine) as session, transfer_lock(session, customer_id):
        pass
    output.close()


def test_simultaneous_transfer_requests_only_create_one_copy(isolated_postgres):
    _url, _schema, engine = isolated_postgres
    from app.models.router import Router

    customer = _customer()
    with Session(engine) as setup:
        setup.add_all(
            [
                Router(
                    id="old-hostel", name="Old", vpn_host="old.test", hotspot_network="10.1.0.0/24"
                ),
                Router(
                    id="new-hostel", name="New", vpn_host="new.test", hotspot_network="10.2.0.0/24"
                ),
            ]
        )
        setup.flush()
        setup.add(customer)
        setup.commit()
        customer_id = customer.id
    from app.models.customer import Customer

    source = FakeTransferClient(_user(**{"limit-bytes-total": "1000", "bytes-in": "400"}))
    destination = FakeTransferClient()
    entered, release = threading.Event(), threading.Event()
    mutate = source.mutate_hotspot_transfer_user

    def block_claim(expected, **kwargs):
        if not kwargs.get("remove"):
            entered.set()
            assert release.wait(30)
        return mutate(expected, **kwargs)

    source.mutate_hotspot_transfer_user = block_claim
    outcomes = []

    def first():
        with Session(engine, expire_on_commit=False) as session:
            session.customer = session.get(Customer, customer_id)
            try:
                outcomes.append(_move(source, destination, session))
            except Exception as exc:  # noqa: BLE001 - Surface thread failures to the test.
                outcomes.append(exc)

    worker = threading.Thread(target=first)
    worker.start()
    try:
        assert entered.wait(30)
        with Session(engine, expire_on_commit=False) as session:
            session.customer = session.get(Customer, customer_id)
            with pytest.raises(ServiceError) as error:
                _move(source, destination, session)
            assert error.value.error_code == "hostel_transfer_in_progress"
    finally:
        release.set()
        worker.join(30)
    assert not worker.is_alive()
    assert len(outcomes) == 1 and not isinstance(outcomes[0], Exception)
    assert destination.events.count("create-copy") == 1
    assert source.user is None and destination.user["limit-bytes-total"] == "600"


def test_migration_upgrade_matches_model_and_downgrade_preserves_pending_journal(
    isolated_postgres, monkeypatch
):
    url, schema, engine = isolated_postgres
    from sqlalchemy import inspect

    # Start with the previous schema in this private test schema.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE hostel_transfer_operations"))
    migration_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("DATABASE_URL", migration_url.render_as_string(hide_password=False))
    from app.core.config import get_settings

    get_settings.cache_clear()
    config = Config("alembic.ini")
    try:
        command.stamp(config, "20261008_0014")
        command.upgrade(config, "head")
        inspector = inspect(engine)
        actual = {column["name"] for column in inspector.get_columns("hostel_transfer_operations")}
        assert actual == set(Base.metadata.tables["hostel_transfer_operations"].columns.keys())
        indexes = inspector.get_indexes("hostel_transfer_operations")
        assert any(
            index["name"] == "uq_hostel_transfer_active_customer" and index["unique"]
            for index in indexes
        )
        # An active journal is protected even if an operator attempts downgrade.
        from app.models.hostel_transfer import HostelTransferOperation
        from app.models.router import Router

        customer = _customer()
        with Session(engine) as session:
            session.add_all(
                [
                    Router(id="old-hostel", name="Old", vpn_host="old.test"),
                    Router(id="new-hostel", name="New", vpn_host="new.test"),
                ]
            )
            session.flush()
            session.add(customer)
            session.flush()
            session.add(
                HostelTransferOperation(
                    customer_id=customer.id,
                    username=customer.username,
                    source_router_id="old-hostel",
                    destination_router_id="new-hostel",
                    destination_router_name="New",
                    source_user_id="*1",
                    actor_type="customer",
                )
            )
            session.commit()
        with pytest.raises(RuntimeError, match="Unfinished hostel transfers"):
            command.downgrade(config, "20261008_0014")
        assert inspect(engine).has_table("hostel_transfer_operations")
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE hostel_transfer_operations SET is_active=false, status='rolled_back'")
            )
        command.downgrade(config, "20261008_0014")
        assert not inspect(engine).has_table("hostel_transfer_operations")
    finally:
        get_settings.cache_clear()
