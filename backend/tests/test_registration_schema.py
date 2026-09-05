import pytest
from pydantic import ValidationError

from app.schemas.registration import RegistrationCompleteRequest, RegistrationStartRequest


def test_registration_contract_normalizes_identity_and_keeps_hostel_assignment() -> None:
    request = RegistrationStartRequest(
        email="  AMA@Example.COM ",
        username=" AmaB ",
        router_id=" platinum ",
        pin="483265",
    )

    assert request.email == "ama@example.com"
    assert request.username == "amab"
    assert request.router_id == "platinum"
    assert request.pin.get_secret_value() == "483265"
    assert "483265" not in repr(request)


@pytest.mark.parametrize("pin", ["", "12345", "1234567", "12ab56", "１２３４５６"])
def test_registration_contract_rejects_invalid_pin(pin: str) -> None:
    with pytest.raises(ValidationError):
        RegistrationStartRequest(
            email="ama@example.com",
            username="amab",
            router_id="platinum",
            pin=pin,
        )


def test_registration_completion_keeps_pin_and_code_out_of_repr() -> None:
    request = RegistrationCompleteRequest(
        challenge_id="66888786-57ac-49cb-b240-bad9a4dcd769",
        email="ama@example.com",
        username="amab",
        router_id="platinum",
        pin="483265",
        code="042731",
    )

    assert "483265" not in repr(request)
    assert "042731" not in repr(request)


@pytest.mark.parametrize("username", ["ama.b", "ama_b", "ama-b", "ama b", "ama@b"])
def test_registration_contract_rejects_special_characters(username: str) -> None:
    with pytest.raises(ValidationError):
        RegistrationStartRequest(
            email="ama@example.com",
            username=username,
            router_id="platinum",
            pin="483265",
        )
