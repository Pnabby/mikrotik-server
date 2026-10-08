"""Availability and error reporting with isolated databases and fake APIs."""

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from routeros_api.exceptions import RouterOsApiConnectionError, RouterOsApiError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from test_hostel_transfer import (
    TEST_CIPHER,
    AcceptingPinHasher,
    FakeSession,
    FakeTransferClient,
    _customer,
    _move,
    _user,
)

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.core.transfer_errors import TRANSFER_ERROR_DETAILS
from app.core.transfer_security import TransferSnapshotCipher
from app.dependencies import mikrotik_client_context
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.integrations.mikrotik.registry import RouterDefinition
from app.main import app
from app.models.admin_user import AdminUser
from app.models.customer import Customer
from app.models.enums import AdminRole, RouterStatus
from app.models.hostel_transfer import HostelTransferOperation
from app.models.router import Router
from app.routes import account, admin_dashboard
from app.schemas.account import HostelTransferRequest
from app.schemas.admin_dashboard import AdminCustomerTransferRequest
from app.services.hostel_transfer import HostelTransferService
from app.services.hostel_transfer_availability import resolve_transfer_routers
from app.services.hostel_transfer_recovery import HostelTransferRecovery


@pytest.fixture
def routers():
    session = FakeSession(_customer())
    source = FakeTransferClient(_user(**{"limit-bytes-total": "1000", "bytes-in": "400"}))
    destination = FakeTransferClient()
    yield session, source, destination
    engine = session.get_bind()
    session.close()
    engine.dispose()


def no_changes(session, source, destination):
    assert source.user["disabled"] == "no"
    assert source.user["limit-bytes-total"] == "1000"
    assert destination.user is None
    assert session.get(Customer, session.customer.id).router_id == "old-hostel"
    assert session.scalar(select(HostelTransferOperation.id)) is None
    assert not {"mutate-user", "clear-auth", "delete-user"}.intersection(source.events)
    assert "create-copy" not in destination.events


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize(
    "failure,reason",
    [
        (RouterOsApiConnectionError("secret endpoint"), "unreachable"),
        (TimeoutError("secret endpoint"), "unreachable"),
        (RouterOsApiError("cannot log in with secret password"), "authentication_failed"),
        (RouterOsApiError("not enough permissions for secret script"), "permission_denied"),
        (RouterOsApiError("no such command secret script"), "commands_unavailable"),
        (RouterOsApiError("API rejected secret payload"), "request_failed"),
    ],
)
def test_both_routers_checked_and_failed_side_identified(
    routers, monkeypatch, caplog, side, failure, reason
):
    session, source, destination = routers
    client = source if side == "source" else destination

    def unavailable():
        client.events.append("check-availability")
        raise failure

    monkeypatch.setattr(client, "check_transfer_availability", unavailable)
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == f"hostel_{side}_router_{reason}"
    assert source.events == destination.events == ["check-availability"]
    no_changes(session, source, destination)
    assert "secret" not in caplog.text
    response = asyncio.run(app.exception_handlers[ServiceError](None, error.value))
    payload = json.loads(response.body)
    assert payload["detail"] == TRANSFER_ERROR_DETAILS[error.value.error_code]
    assert "secret" not in response.body.decode()
    assert "temporarily unavailable" not in payload["detail"]


def test_both_failures_reported_without_creating_recovery_operation(routers, monkeypatch):
    session, source, destination = routers
    for client in (source, destination):

        def unavailable(client=client):
            client.events.append("check-availability")
            raise RouterOsApiConnectionError("offline")

        monkeypatch.setattr(client, "check_transfer_availability", unavailable)
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == "hostel_both_routers_not_ready"
    assert error.value.field_errors == {
        "source": "hostel_source_router_unreachable",
        "destination": "hostel_destination_router_unreachable",
    }
    assert source.events == destination.events == ["check-availability"]
    no_changes(session, source, destination)


def test_router_becomes_available_next_attempt_can_complete(routers, monkeypatch):
    session, source, destination = routers
    probe = destination.check_transfer_availability
    monkeypatch.setattr(
        destination, "check_transfer_availability", lambda: (_ for _ in ()).throw(TimeoutError())
    )
    with pytest.raises(ServiceError):
        _move(source, destination, session)
    no_changes(session, source, destination)
    monkeypatch.setattr(destination, "check_transfer_availability", probe)
    result = _move(source, destination, session)
    assert result.router_id == "new-hostel"
    assert result.remaining_data_limit_bytes == 600
    assert source.user is None and destination.user["disabled"] == "no"
    assert session.customer.router_id == "new-hostel"


@pytest.mark.parametrize(
    "side,method",
    [
        ("source", "get_hotspot_user"),
        ("destination", "get_hotspot_user"),
        ("source", "get_hotspot_user_profile"),
        ("destination", "get_hotspot_user_profile"),
    ],
)
def test_read_failure_after_probe_still_prevents_account_changes(
    routers, monkeypatch, side, method
):
    session, source, destination = routers
    client = source if side == "source" else destination

    def rejected(_value):
        raise RouterOsApiError("not enough permissions")

    monkeypatch.setattr(client, method, rejected)
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == f"hostel_{side}_router_permission_denied"
    no_changes(session, source, destination)


def test_missing_recovery_migration_is_not_a_router_outage(routers):
    session, source, destination = routers
    HostelTransferOperation.__table__.drop(session.get_bind())
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == "hostel_transfer_storage_unavailable"
    assert source.events == destination.events == []
    assert source.user["disabled"] == "no" and destination.user is None


def test_cipher_configuration_failure_is_not_a_router_outage(routers, monkeypatch):
    session, source, destination = routers

    def not_configured(_settings):
        raise ValueError("secret configuration")

    monkeypatch.setattr(TransferSnapshotCipher, "from_settings", not_configured)
    with pytest.raises(ServiceError) as error:
        HostelTransferService(session).transfer_with_pin(
            session.customer,
            pin="123456",
            pin_hasher=AcceptingPinHasher(),
            destination_router_id="new-hostel",
            destination_router_name="New Hostel",
            source_client=source,
            destination_client=destination,
            ip_address=None,
        )
    assert error.value.error_code == "hostel_transfer_not_configured"
    no_changes(session, source, destination)


def test_database_checkpoint_failure_is_not_a_router_outage(routers, monkeypatch):
    session, source, destination = routers

    def failed_commit():
        raise SQLAlchemyError("secret database connection")

    monkeypatch.setattr(session, "commit", failed_commit)
    with pytest.raises(ServiceError) as error:
        _move(source, destination, session)
    assert error.value.error_code == "hostel_transfer_storage_unavailable"
    no_changes(session, source, destination)


def test_application_probe_error_is_not_reported_as_router_unavailable(routers, monkeypatch):
    session, source, destination = routers

    def broken_adapter():
        raise TypeError("invalid adapter arguments")

    monkeypatch.setattr(source, "check_transfer_availability", broken_adapter)
    with pytest.raises(TypeError):
        _move(source, destination, session)
    no_changes(session, source, destination)


@pytest.mark.parametrize("side", ["source", "destination"])
def test_recovery_checks_both_routers_then_resumes_move_when_available(routers, monkeypatch, side):
    session, source, destination = routers

    class ProcessStopped(BaseException):
        pass

    copy = destination.create_hotspot_user_copy

    def process_stops(*_args, **_kwargs):
        raise ProcessStopped()

    monkeypatch.setattr(destination, "create_hotspot_user_copy", process_stops)
    with pytest.raises(ProcessStopped):
        _move(source, destination, session)
    operation = session.scalar(select(HostelTransferOperation))
    assert source.user["disabled"] == "yes" and destination.user is None
    source.events.clear()
    destination.events.clear()
    client = source if side == "source" else destination
    probe = client.check_transfer_availability

    def unavailable():
        client.events.append("check-availability")
        raise RouterOsApiConnectionError("secret connection")

    monkeypatch.setattr(client, "check_transfer_availability", unavailable)
    recovery = HostelTransferRecovery(session, TEST_CIPHER)
    attempts = operation.attempt_count
    recovery.run(operation, source, destination, raise_errors=False)
    assert source.events == destination.events == ["check-availability"]
    assert operation.error_code == f"hostel_{side}_router_unreachable"
    assert operation.attempt_count == attempts + 1
    assert not operation.last_confirmed_state.get("rollback_requested")
    assert operation.is_active and source.user["disabled"] == "yes"
    monkeypatch.setattr(client, "check_transfer_availability", probe)
    monkeypatch.setattr(destination, "create_hotspot_user_copy", copy)
    recovery.run(operation, source, destination)
    assert operation.status == "completed" and not operation.is_active
    assert session.customer.router_id == "new-hostel"
    assert source.user is None and destination.user["disabled"] == "no"
    assert destination.user["limit-bytes-total"] == "600"


@pytest.mark.parametrize("side", ["source", "destination"])
def test_missing_catalogue_configuration_is_not_a_router_outage(routers, side):
    session, source, destination = routers
    ids = ["old-hostel", "new-hostel"]
    ids[0 if side == "source" else 1] = "unknown-hostel"
    with pytest.raises(ServiceError) as error:
        resolve_transfer_routers(session, *ids)
    assert error.value.error_code == f"hostel_{side}_router_not_configured"
    no_changes(session, source, destination)


def test_real_client_checks_authenticated_hotspot_menus_and_synchronous_script():
    calls = []

    class Api:
        def get_resource(self, path):
            class Resource:
                def get(self):
                    calls.append((path, "print"))
                    return [{"name": "Test router"}]

                def call(self, command, args):
                    calls.append((path, command, args))
                    return SimpleNamespace(done_message={"ret": "hostel-transfer-ready\n"})

            return Resource()

    client = MikroTikClient(MikroTikConfig(host="unused.test", username="test", password="test"))
    client._api = Api()
    client.check_transfer_availability()
    assert calls[0] == ("/system/identity", "print")
    assert {call[0] for call in calls[1:-1]} == {
        "/ip/hotspot/user",
        "/ip/hotspot/user/profile",
        "/ip/hotspot/active",
        "/ip/hotspot/cookie",
    }
    assert all(call[1:] == ("print", {"count-only": ""}) for call in calls[1:-1])
    assert calls[-1] == (
        "/",
        "execute",
        {"script": ':put "hostel-transfer-ready"', "as-string": ""},
    )


@pytest.mark.parametrize("ret", ["*1", "", "unexpected response"])
def test_unconfirmed_script_probe_never_treated_as_ready(ret):
    class Api:
        def get_resource(self, _path):
            return SimpleNamespace(
                get=lambda: [{"name": "Router"}],
                call=lambda *_args: SimpleNamespace(done_message={"ret": ret}),
            )

    client = MikroTikClient(MikroTikConfig(host="unused.test", username="test", password="test"))
    client._api = Api()
    with pytest.raises(RouterOsApiError):
        client.check_transfer_availability()


def test_disconnect_failure_does_not_mask_success_or_application_errors(monkeypatch, caplog):
    router = RouterDefinition("test", "Test", "unused.test", 8728, "10.1.0.0/24")
    monkeypatch.setattr(
        MikroTikConfig,
        "from_env",
        lambda _router: MikroTikConfig(host="unused.test", username="test", password="test"),
    )

    def failed_close(_client):
        raise OSError("secret connection details")

    monkeypatch.setattr(MikroTikClient, "disconnect", failed_close)
    with mikrotik_client_context(router):
        pass
    for failure in (SQLAlchemyError("database failure"), ValueError("application failure")):
        with pytest.raises(type(failure)) as error, mikrotik_client_context(router):
            raise failure
        assert error.value is failure
    assert "secret" not in caplog.text


def test_disconnect_clears_pool_even_when_close_fails():
    client = MikroTikClient(MikroTikConfig(host="unused.test", username="test", password="test"))

    def failed_close():
        raise OSError("closed")

    client._pool = SimpleNamespace(disconnect=failed_close)
    client._api = object()
    with pytest.raises(OSError):
        client.disconnect()
    assert client._pool is None and client._api is None


@pytest.mark.parametrize("actor", ["customer", "admin"])
def test_both_entry_points_probe_before_mutation_and_move_despite_cached_offline_status(
    routers, monkeypatch, actor
):
    session, source, destination = routers
    for router in session.scalars(select(Router)):
        router.status = RouterStatus.OFFLINE
    settings = Settings(pin_hash_secret="test-transfer-secret-with-at-least-32-characters")
    monkeypatch.setattr("app.services.hostel_transfer.get_settings", lambda: settings)
    module = account if actor == "customer" else admin_dashboard
    shared_events = []

    @contextmanager
    def context(router):
        client = source if router.router_id == "old-hostel" else destination
        yield client

    monkeypatch.setattr(module, "mikrotik_client_context", context)
    for side, client in (("source", source), ("destination", destination)):
        probe = client.check_transfer_availability

        def record_probe(side=side, probe=probe):
            shared_events.append(side)
            probe()

        monkeypatch.setattr(client, "check_transfer_availability", record_probe)
    mutate = source.mutate_hotspot_transfer_user

    def checked_mutation(*args, **kwargs):
        assert shared_events == ["source", "destination"]
        return mutate(*args, **kwargs)

    monkeypatch.setattr(source, "mutate_hotspot_transfer_user", checked_mutation)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    if actor == "customer":
        monkeypatch.setattr(
            account.Argon2PinHasher, "from_settings", lambda _settings: AcceptingPinHasher()
        )
        result = account.transfer_customer_hostel(
            HostelTransferRequest(destination_router_id="new-hostel", pin="123456"),
            request,
            session.customer,
            session,
            settings,
        )
    else:
        admin = AdminUser(
            email="test-admin@example.com",
            password_hash="test-password",
            role=AdminRole.ADMINISTRATOR,
        )
        session.add(admin)
        session.commit()
        monkeypatch.setattr(admin_dashboard, "Argon2PasswordHasher", AcceptingPinHasher)
        result = admin_dashboard.transfer_customer_hostel(
            session.customer.id,
            AdminCustomerTransferRequest(
                destination_router_id="new-hostel", password="test-password"
            ),
            request,
            admin,
            session,
        )
    assert result.router_id == session.customer.router_id == "new-hostel"
    assert result.hostel_name == "New Hostel"
    assert result.remaining_data_limit_bytes == 600
    assert source.user is None
    assert destination.user["name"] == "ama" and destination.user["password"] == "123456"
    assert destination.user["disabled"] == "no"
    assert session.scalar(select(HostelTransferOperation)).status == "completed"
