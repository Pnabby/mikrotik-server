import json
import uuid
from decimal import Decimal
from types import SimpleNamespace

import httpx

from app.core.config import Settings
from app.integrations.paystack import InitializedTransaction, PaystackClient
from app.services.payment_verification import PaymentVerificationService


class FakeSession:
    def __init__(self, mapping) -> None:
        self.mapping = mapping
        self.added = []
        self.commits = 0

    def scalar(self, _query):
        return self.mapping

    def add_all(self, values) -> None:
        self.added.extend(values)

    def commit(self) -> None:
        self.commits += 1


class RecordingGateway:
    def __init__(self) -> None:
        self.initialize_arguments = None

    def initialize_transaction(self, **arguments):
        self.initialize_arguments = arguments
        return InitializedTransaction(
            authorization_url="https://checkout.paystack.com/access-code",
            access_code="access-code",
            reference=arguments["reference"],
        )

    def verify_transaction(self, _reference):
        raise AssertionError("Verification should not run during initialization.")


def test_checkout_uses_split_code_from_customers_hostel() -> None:
    package_id = uuid.uuid4()
    customer = SimpleNamespace(
        id=uuid.uuid4(),
        router_id="hall",
        email="student@example.com",
        username="student",
    )
    mapping = SimpleNamespace(
        package=SimpleNamespace(
            id=package_id,
            amount=Decimal("15.00"),
            currency="GHS",
            is_promotional=False,
            name="Weekly",
        ),
        router=SimpleNamespace(paystack_split_code="SPL_hall123"),
        mikrotik_profile="weekly",
        display_name="Hall Weekly",
    )
    session = FakeSession(mapping)
    gateway = RecordingGateway()
    service = PaymentVerificationService(
        session,
        Settings(paystack_callback_url="https://wifi.example/api/payments/paystack/callback"),
        gateway,
        lambda _router_id: None,
    )
    service._ensure_router_ready = lambda **_arguments: None
    service._next_sqlite_sequence = lambda: None

    service.initialize(customer, package_id)

    assert gateway.initialize_arguments["split_code"] == "SPL_hall123"
    assert gateway.initialize_arguments["metadata"]["router_id"] == "hall"


def test_paystack_client_sends_split_code_as_top_level_field() -> None:
    captured_payload = None

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/access-code",
                    "access_code": "access-code",
                    "reference": "VLAD-REFERENCE",
                },
            },
        )

    client = PaystackClient(
        secret_key="sk_test_example",
        transport=httpx.MockTransport(respond),
    )

    client.initialize_transaction(
        email="student@example.com",
        amount=1500,
        currency="GHS",
        reference="VLAD-REFERENCE",
        callback_url="https://wifi.example/callback",
        metadata={"router_id": "hall"},
        split_code=" SPL_hall123 ",
    )

    assert captured_payload["split_code"] == "SPL_hall123"
    assert "split_code" not in captured_payload["metadata"]


def test_paystack_client_omits_empty_split_code() -> None:
    captured_payload = None

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/access-code",
                    "access_code": "access-code",
                    "reference": "VLAD-REFERENCE",
                },
            },
        )

    client = PaystackClient(
        secret_key="sk_test_example",
        transport=httpx.MockTransport(respond),
    )

    client.initialize_transaction(
        email="student@example.com",
        amount=1500,
        currency="GHS",
        reference="VLAD-REFERENCE",
        callback_url="https://wifi.example/callback",
        metadata={"router_id": "hall"},
    )

    assert "split_code" not in captured_payload
