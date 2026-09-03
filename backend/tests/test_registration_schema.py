import pytest
from pydantic import ValidationError

from app.schemas.registration import RegistrationStartRequest


def test_registration_contract_normalizes_identity_and_keeps_hostel_assignment() -> None:
    request = RegistrationStartRequest(
        email="  AMA@Example.COM ",
        username=" Ama.B ",
        router_id=" platinum ",
        pin="483265",
    )

    assert request.email == "ama@example.com"
    assert request.username == "ama.b"
    assert request.router_id == "platinum"
    assert request.pin.get_secret_value() == "483265"
    assert "483265" not in repr(request)


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "12ab56", "１２３４５６"])
def test_registration_contract_rejects_invalid_pin(pin: str) -> None:
    with pytest.raises(ValidationError):
        RegistrationStartRequest(
            email="ama@example.com",
            username="ama.b",
            router_id="platinum",
            pin=pin,
        )
