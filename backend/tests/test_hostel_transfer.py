import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import ServiceError
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.main import app
from app.models.customer import Customer
from app.services.hostel_transfer import HostelTransferService, _remaining_byte_limits


class AcceptingPinHasher:
    def hash(self, pin: str) -> str:
        return pin

    def verify(self, pin_hash: str, pin: str) -> bool:
        return pin_hash == pin


class FakeSession:
    def __init__(self, customer=None) -> None:
        self.added = []
        self.commits = 0
        self.customer = customer

    def scalar(self, _query):
        return self.customer

    def scalars(self, _query):
        return []

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass


class FakeTransferClient:
    def __init__(self, user=None, *, profile_exists=True, settled_user=None) -> None:
        self.user = dict(user) if user else None
        self.profile_exists = profile_exists
        self.settled_user = dict(settled_user) if settled_user else None
        self.events = []
        self.copied_limits = None

    def get_hotspot_user(self, _username):
        self.events.append("read-user")
        return dict(self.user) if self.user else None

    def get_hotspot_user_profile(self, _profile):
        self.events.append("read-profile")
        return {"name": "paid"} if self.profile_exists else None

    def clear_hotspot_authentication(self, _username):
        self.events.append("clear-auth")
        if self.settled_user is not None:
            self.user = dict(self.settled_user)
        return dict(self.user) if self.user else None

    def create_hotspot_user_copy(self, user, *, byte_limits):
        self.events.append("create-copy")
        self.user = dict(user)
        for field, remaining in byte_limits.items():
            self.user[field] = str(0 if remaining is None else max(1, remaining))
        self.copied_limits = dict(byte_limits)
        return dict(self.user)

    def delete_hotspot_user(self, _username):
        self.events.append("delete-user")
        self.user = None
        return True


class FakeRouterResource:
    def __init__(self, records=None) -> None:
        self.records = list(records or [])
        self.added = None

    def get(self, **filters):
        if not filters:
            return [dict(record) for record in self.records]
        return [
            dict(record)
            for record in self.records
            if all(record.get(key) == value for key, value in filters.items())
        ]

    def add(self, **attributes):
        self.added = dict(attributes)
        self.records.append({"id": "*1", **attributes})


class FakeRouterApi:
    def __init__(self) -> None:
        self.users = FakeRouterResource()
        self.profiles = FakeRouterResource([{"name": "paid"}])

    def get_resource(self, path):
        if path == "/ip/hotspot/user":
            return self.users
        if path == "/ip/hotspot/user/profile":
            return self.profiles
        raise AssertionError(f"Unexpected resource: {path}")


def _customer() -> Customer:
    return Customer(
        id=uuid.uuid4(),
        router_id="old-hostel",
        username="ama",
        email="ama@example.com",
        pin_hash="123456",
    )


def test_transfer_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/account/transfer-hostel" in paths
    assert "/api/admin/dashboard/customers/{customer_id}/transfer-hostel" in paths
    assert "/api/admin/dashboard/customers/{customer_id}/delete" in paths


def test_remaining_limits_are_calculated_from_settled_counters() -> None:
    limits = _remaining_byte_limits(
        {
            "limit-bytes-in": "500",
            "limit-bytes-out": "0",
            "limit-bytes-total": "1000",
            "bytes-in": "250",
            "bytes-out": "150",
        }
    )

    assert limits == {
        "limit-bytes-in": 250,
        "limit-bytes-out": None,
        "limit-bytes-total": 600,
    }


def test_transfer_clears_auth_before_calculating_and_preserves_comment() -> None:
    original = {
        "name": "ama",
        "password": "123456",
        "profile": "paid",
        "comment": "activation=ACT-123;login=2030-01-01T00:00:00Z",
        "limit-bytes-total": "1000",
        "bytes-in": "100",
        "bytes-out": "50",
        "disabled": "no",
    }
    settled = {**original, "bytes-in": "250", "bytes-out": "150"}
    source = FakeTransferClient(original, settled_user=settled)
    destination = FakeTransferClient()
    customer = _customer()
    session = FakeSession(customer)

    result = HostelTransferService(session).transfer_with_pin(
        customer,
        pin="123456",
        pin_hasher=AcceptingPinHasher(),
        destination_router_id="new-hostel",
        destination_router_name="New Hostel",
        source_client=source,
        destination_client=destination,
        ip_address="127.0.0.1",
    )

    assert source.events.index("clear-auth") < source.events.index("delete-user")
    assert destination.user["comment"] == original["comment"]
    assert destination.copied_limits["limit-bytes-total"] == 600
    assert source.user is None
    assert customer.router_id == "new-hostel"
    assert session.commits == 1
    assert result.remaining_data_limit_bytes == 600


def test_wrong_pin_does_not_touch_either_router() -> None:
    source = FakeTransferClient({"name": "ama", "profile": "paid"})
    destination = FakeTransferClient()

    with pytest.raises(ServiceError) as error:
        customer = _customer()
        HostelTransferService(FakeSession(customer)).transfer_with_pin(
            customer,
            pin="999999",
            pin_hasher=AcceptingPinHasher(),
            destination_router_id="new-hostel",
            destination_router_name="New Hostel",
            source_client=source,
            destination_client=destination,
            ip_address=None,
        )

    assert error.value.status_code == 401
    assert source.events == []
    assert destination.events == []


def test_destination_profile_is_checked_before_old_sessions_are_ended() -> None:
    source = FakeTransferClient(
        {"name": "ama", "password": "123456", "profile": "paid"}
    )
    destination = FakeTransferClient(profile_exists=False)

    with pytest.raises(ServiceError) as error:
        customer = _customer()
        HostelTransferService(FakeSession(customer)).transfer_with_pin(
            customer,
            pin="123456",
            pin_hasher=AcceptingPinHasher(),
            destination_router_id="new-hostel",
            destination_router_name="New Hostel",
            source_client=source,
            destination_client=destination,
            ip_address=None,
        )

    assert error.value.status_code == 409
    assert "clear-auth" not in source.events
    assert source.user is not None


def test_router_copy_only_writes_configurable_fields_and_remaining_quota() -> None:
    api = FakeRouterApi()
    client = MikroTikClient(MikroTikConfig(host="router", username="api", password="secret"))
    client._api = api
    source = {
        "id": "*9",
        "name": "ama",
        "password": "123456",
        "profile": "paid",
        "server": "hotspot1",
        "address": "10.0.0.5",
        "comment": "activation=ACT-123;login=2030-01-01 00:00:00",
        "disabled": "no",
        "bytes-in": "400",
        "bytes-out": "300",
        "uptime": "2h",
        "limit-bytes-total": "1000",
    }

    copied = client.create_hotspot_user_copy(
        source,
        byte_limits={
            "limit-bytes-in": None,
            "limit-bytes-out": None,
            "limit-bytes-total": 300,
        },
    )

    assert copied["comment"] == source["comment"]
    assert api.users.added["password"] == "123456"
    assert api.users.added["address"] == "10.0.0.5"
    assert api.users.added["limit-bytes-total"] == "300"
    assert "bytes-in" not in api.users.added
    assert "bytes-out" not in api.users.added
    assert "uptime" not in api.users.added
    assert "id" not in api.users.added


def test_exhausted_finite_quota_does_not_become_unlimited() -> None:
    api = FakeRouterApi()
    client = MikroTikClient(MikroTikConfig(host="router", username="api", password="secret"))
    client._api = api

    client.create_hotspot_user_copy(
        {
            "name": "ama",
            "password": "123456",
            "profile": "paid",
            "disabled": "no",
        },
        byte_limits={
            "limit-bytes-in": None,
            "limit-bytes-out": None,
            "limit-bytes-total": 0,
        },
    )

    assert api.users.added["limit-bytes-total"] == "1"


def _move(source, destination, session=None):
    customer = session.customer if session else _customer()
    return HostelTransferService(session or FakeSession(customer)).transfer_with_pin(
        customer, pin="123456", pin_hasher=AcceptingPinHasher(),
        destination_router_id="new-hostel", destination_router_name="New Hostel",
        source_client=source, destination_client=destination, ip_address=None,
    )


def _user(**fields):
    return {"name": "ama", "password": "123456", "profile": "paid", "disabled": "no", **fields}


def test_transfer_uses_destination_network_and_deducts_used_uptime():
    source = FakeTransferClient(_user(server="main-hotspot", address="10.1.0.8",
                                     routes="10.1.0.0/24", **{"limit-uptime": "2h", "uptime": "30m"}))
    destination = FakeTransferClient()
    _move(source, destination)
    assert destination.user["server"] == "all"
    assert "address" not in destination.user
    assert "routes" not in destination.user
    assert destination.user["limit-uptime"] == "5400s"


@pytest.mark.parametrize("field,changed", [("rate-limit", "5M/5M"), ("shared-users", "2"),
                                         ("session-timeout", "1h"), ("idle-timeout", "5m")])
def test_mismatched_profiles_do_not_disconnect_source(field, changed):
    source = FakeTransferClient(_user())
    destination = FakeTransferClient()
    source.get_hotspot_user_profile = lambda _: {"name": "paid", "rate-limit": "5M/10M"}
    destination.get_hotspot_user_profile = lambda _: {"name": "paid", "rate-limit": "5M/10M", field: changed}
    with pytest.raises(ServiceError) as error:
        _move(source, destination)
    assert error.value.error_code == "hostel_profile_mismatch"
    assert "clear-auth" not in source.events


def test_failed_destination_readback_retains_source_and_removes_copy():
    source = FakeTransferClient(_user())
    destination = FakeTransferClient()
    copy = destination.create_hotspot_user_copy
    def bad_copy(user, *, byte_limits):
        return {**copy(user, byte_limits=byte_limits), "password": "incorrect"}
    destination.create_hotspot_user_copy = bad_copy
    with pytest.raises(ServiceError):
        _move(source, destination)
    assert source.user is not None
    assert destination.user is None
    assert "delete-user" not in source.events


def test_exhausted_data_account_stays_disabled_after_transfer():
    source = FakeTransferClient(_user(**{"limit-bytes-total": "100", "bytes-in": "100"}))
    destination = FakeTransferClient()
    result = _move(source, destination)
    assert result.remaining_data_limit_bytes == 0
    assert destination.user["disabled"] == "yes"


def test_database_failure_restores_source_before_removing_destination():
    customer = _customer()
    class FailingSession(FakeSession):
        def commit(self):
            raise SQLAlchemyError("database unavailable")
    source = FakeTransferClient(_user(**{"limit-bytes-total": "1000", "bytes-in": "400"}))
    destination = FakeTransferClient()
    destination_delete = destination.delete_hotspot_user
    def verify_restore(username):
        assert source.user is not None
        assert source.user["limit-bytes-total"] == "600"
        return destination_delete(username)
    destination.delete_hotspot_user = verify_restore
    with pytest.raises(ServiceError):
        _move(source, destination, FailingSession(customer))
    assert source.user is not None
    assert destination.user is None
