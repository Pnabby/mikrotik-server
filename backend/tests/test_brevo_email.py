import httpx

from app.integrations.brevo.client import BrevoEmailSender


def test_brevo_sender_uses_transactional_email_api_without_exposing_key() -> None:
    captured: dict[str, object] = {}

    def accept_email(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"messageId": "test-message"})

    sender = BrevoEmailSender(
        api_key="test-brevo-api-key",
        sender_email="wifi@example.com",
        sender_name="Flint WiFi",
        transport=httpx.MockTransport(accept_email),
    )

    sender.send_registration_otp(
        recipient="ama@example.com",
        code="042731",
        expires_in_minutes=10,
    )

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.url == "https://api.brevo.com/v3/smtp/email"
    assert request.headers["api-key"] == "test-brevo-api-key"
    body = request.read().decode()
    assert "ama@example.com" in body
    assert "042731" in body
    assert "wifi@example.com" in body
    assert "test-brevo-api-key" not in body
    assert "test-brevo-api-key" not in repr(sender)
