import pytest
from pydantic import ValidationError

from app.schemas.registration import normalize_phone_number


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("024 123 4567", "+233241234567"),
        ("0241234567", "+233241234567"),
        ("233241234567", "+233241234567"),
        ("+233241234567", "+233241234567"),
    ],
)
def test_normalize_ghana_phone_number(value: str, expected: str) -> None:
    assert normalize_phone_number(value) == expected


@pytest.mark.parametrize("value", ["", "024123", "+0233241234567", "not-a-number"])
def test_reject_invalid_phone_number(value: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        normalize_phone_number(value)
