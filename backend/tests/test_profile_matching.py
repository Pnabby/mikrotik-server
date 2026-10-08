import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ServiceError
from app.integrations.mikrotik.client import MikroTikClient, MikroTikConfig
from app.schemas.admin_profiles import AdminProfileUpdate, AdminRouterProfileSettings
from app.services.admin_profiles import AdminProfileService
from app.services.profile_settings import profile_differences


class ProfileResource:
    def __init__(self, profiles):
        self.records = profiles
        self.writes = []

    def get(self, **filters):
        return [dict(p) for p in self.records if all(p.get(k) == v for k, v in filters.items())]

    def add(self, **values):
        self.writes.append(values)
        self.records.append({"id": "*2", **values})

    def set(self, **values):
        self.writes.append(values)
        record = next(p for p in self.records if p["id"] == values["id"])
        record.update(values)


class ProfileApi:
    def __init__(self, resource):
        self.resource = resource

    def get_resource(self, path):
        assert path == "/ip/hotspot/user/profile"
        return self.resource


def client_for(profiles):
    resource = ProfileResource(profiles)
    client = MikroTikClient(MikroTikConfig(host="test", username="api", password="test"))
    client._api = ProfileApi(resource)
    return client, resource


def test_equivalent_router_speed_and_timeout_formats_match():
    assert (
        profile_differences(
            {"rate-limit": "5M/10.0M", "session-timeout": "1h", "keepalive-timeout": "2m"},
            {
                "rate-limit": "5000k/10000000",
                "session-timeout": "01:00:00",
                "keepalive-timeout": "00:02:00",
            },
        )
        == []
    )
    assert profile_differences({"rate-limit": "10M"}, {"rate-limit": "10M/10M"}) == []
    assert profile_differences({"rate-limit": ""}, {"rate-limit": "0/0"}) == []


@pytest.mark.parametrize(
    "settings",
    [
        {"rate_limit": "10 Mbps"},
        {"shared_users": 0},
        {"session_timeout": "tomorrow"},
        {"rate_limit": "1M/2M; /system reboot"},
        {"idle_timeout": "00:99:00"},
    ],
)
def test_invalid_router_settings_are_rejected(settings):
    with pytest.raises(ValidationError):
        AdminRouterProfileSettings(**settings)


def test_profile_creation_copies_login_hooks_and_omits_source_network_dependencies(support_db):
    session, _, admin, source, destination = support_db
    client, resource = client_for([])
    source_profile = {
        "id": "*1",
        "name": "paid",
        "on-login": ":log info $user;",
        "address-pool": "main-pool",
        "parent-queue": "main-queue",
    }
    saved = AdminProfileService(session, Settings()).save_profile(
        router=destination,
        router_client=client,
        mikrotik_profile="paid",
        update=AdminProfileUpdate(
            display_name="Weekly",
            amount=10,
            is_visible=True,
            source_router_id=source.id,
            router_settings=AdminRouterProfileSettings(rate_limit="5M/10M", shared_users=3),
        ),
        admin=admin,
        ip_address=None,
        source_profile=source_profile,
    )
    assert saved.available_on_router
    assert saved.download_speed == "10 Mbps"
    assert saved.device_limit == 3
    assert resource.writes[0]["on-login"] == source_profile["on-login"]
    assert "address-pool" not in resource.writes[0]
    assert "parent-queue" not in resource.writes[0]


def test_existing_profile_speed_and_devices_are_written_to_router_and_catalogue(support_db):
    session, _, admin, source, _ = support_db
    client, resource = client_for([{"id": "*1", "name": "paid", "address-pool": "local-pool"}])
    saved = AdminProfileService(session, Settings()).save_profile(
        router=source,
        router_client=client,
        mikrotik_profile="paid",
        update=AdminProfileUpdate(
            display_name="Weekly",
            amount=10,
            download_speed="Wrong label",
            router_settings=AdminRouterProfileSettings(rate_limit="2M/8M", shared_users=2),
        ),
        admin=admin,
        ip_address=None,
    )
    assert resource.records[0]["rate-limit"] == "2M/8M"
    assert resource.records[0]["address-pool"] == "local-pool"
    assert saved.download_speed == "8 Mbps"
    assert saved.device_limit == 2


def test_missing_profile_requires_an_explicit_source(support_db):
    session, _, admin, source, _ = support_db
    client, resource = client_for([])
    with pytest.raises(ServiceError) as error:
        AdminProfileService(session, Settings()).save_profile(
            router=source,
            router_client=client,
            mikrotik_profile="paid",
            update=AdminProfileUpdate(display_name="Weekly", amount=10),
            admin=admin,
            ip_address=None,
        )
    assert error.value.status_code == 404
    assert resource.writes == []


def test_transferred_account_preserves_plan_presentation_and_purchase(support_db):
    from app.models.activation import Activation
    from app.models.enums import ActivationStatus, PaymentStatus, SubscriptionStatus
    from app.models.package import Package, RouterPackageProfile
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction
    from app.services.customer_account import CustomerAccountService

    session, customers, _, source, destination = support_db
    customer = customers[0]
    package = Package(code="weekly", name="Weekly", amount=10, duration_seconds=604800)
    session.add(package)
    session.flush()
    mapping = RouterPackageProfile(
        router_id=source.id,
        package_id=package.id,
        mikrotik_profile="paid",
        download_speed="10 Mbps",
        display_name="Weekly Freedom",
    )
    transaction = Transaction(
        customer_id=customer.id,
        package_id=package.id,
        router_id=source.id,
        paystack_reference="paid-test",
        amount=10,
        payment_status=PaymentStatus.SUCCESS,
    )
    session.add_all([mapping, transaction])
    session.flush()
    activation = Activation(
        customer_id=customer.id,
        transaction_id=transaction.id,
        package_id=package.id,
        router_id=source.id,
        target_profile="paid",
        status=ActivationStatus.SUCCESS,
        sequence_number=1,
    )
    session.add(activation)
    session.flush()
    session.add(
        Subscription(
            customer_id=customer.id,
            package_id=package.id,
            transaction_id=transaction.id,
            activation_id=activation.id,
            router_id=destination.id,
            status=SubscriptionStatus.ACTIVE,
        )
    )
    customer.router_id = destination.id
    session.commit()
    account = CustomerAccountService(session).overview(customer)
    assert account.hostel_name == "Flint Annex"
    assert account.current_plan.name == "Weekly Freedom"
    assert account.current_plan.download_speed == "10 Mbps"
    assert account.current_plan.duration_seconds == 604800
    assert account.purchases[0].reference == "paid-test"


def test_matching_creates_the_exact_profile_name_when_destination_case_differs(support_db):
    session, _, admin, source, destination = support_db
    client, _resource = client_for([{"id": "*1", "name": "Paid", "rate-limit": "1M/1M"}])
    saved = AdminProfileService(session, Settings()).save_profile(
        router=destination,
        router_client=client,
        mikrotik_profile="paid",
        update=AdminProfileUpdate(
            display_name="Weekly",
            amount=10,
            source_router_id=source.id,
            router_settings=AdminRouterProfileSettings(rate_limit="5M/10M"),
        ),
        admin=admin,
        ip_address=None,
        source_profile={"name": "paid"},
    )
    assert saved.mikrotik_profile == "paid"
    assert client.get_hotspot_user_profile("paid")["rate-limit"] == "5M/10M"
    assert client.get_hotspot_user_profile("Paid")["rate-limit"] == "1M/1M"
    listed = AdminProfileService(session, Settings()).list_profiles(destination, client)
    assert {profile.mikrotik_profile for profile in listed} == {"paid", "Paid"}
