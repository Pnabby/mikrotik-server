import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.routes import pages
from app.schemas.registration import normalize_phone_number


def test_phone_verification_page_is_served_by_spa_fallback() -> None:
    page_paths = {route.path for route in pages.router.routes}

    assert "/verify-phone" in page_paths
    assert "/forgot-password" in page_paths

    response = TestClient(app).get("/verify-phone", follow_redirects=False)
    assert response.status_code in {200, 307}


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
