import logging
import traceback
from unittest.mock import Mock

import httpx
import pytest

from app.integrations.mnotify import MNotifySmsSender, SmsDeliveryError


def accepted_payload():
    return {
        "status": "success",
        "code": "2000",
        "summary": {
            "_id": "campaign-test-123",
            "total_sent": 1,
            "total_rejected": 0,
            "numbers_sent": ["233241234567"],
        },
    }


@pytest.fixture
def provider(monkeypatch):
    response = Mock()
    response.json.return_value = accepted_payload()
    post = Mock(return_value=response)
    monkeypatch.setattr("app.integrations.mnotify.client.httpx.post", post)
    sender = MNotifySmsSender(
        api_url="https://api.mnotify.com/api/sms/quick",
        api_key="private-test-api-key",
        sender_id="VladWiFi",
        timeout=10,
    )
    return sender, post, response


@pytest.mark.parametrize("method", ["send_verification_otp", "send_pin_reset_otp"])
def test_verification_messages_use_otp_route_to_phone(provider, method, caplog):
    sender, post, _ = provider
    caplog.set_level(logging.INFO)
    getattr(sender, method)(recipient="+233241234567", code="135790", expires_in_minutes=10)
    body = post.call_args.kwargs["json"]
    assert body["recipient"] == ["233241234567"]
    assert body["sms_type"] == "otp"
    assert body["is_schedule"] is False
    assert "135790" in body["message"]
    assert "campaign-test-123" in caplog.text
    assert "135790" not in caplog.text
    assert "233241234567" not in caplog.text
    assert "private-test-api-key" not in caplog.text


def test_general_notifications_keep_standard_sms(provider):
    sender, post, _ = provider
    sender.send(recipient="+233241234567", message="Your plan is active.")
    assert "sms_type" not in post.call_args.kwargs["json"]


@pytest.mark.parametrize("payload", [
    {},
    [],
    None,
    {"code": "2000"},
    {"status": "success", "code": "4001"},
    {"status": "error", "code": "2000"},
    {"status": "success", "code": "2000"},
    {"status": "success", "code": "2000", "summary": []},
    {"status": "success", "code": "2000", "summary": {"total_sent": 0, "total_rejected": 1}},
    {"status": "success", "code": "2000", "summary": {"total_sent": 0, "total_rejected": 0}},
    {"status": "success", "code": "2000", "summary": {"total_sent": 1}},
])
def test_http_success_does_not_hide_provider_rejection(provider, payload):
    sender, _, response = provider
    response.json.return_value = payload
    with pytest.raises(SmsDeliveryError):
        sender.send_verification_otp(recipient="+233241234567", code="135790", expires_in_minutes=10)


def test_transport_failure_does_not_expose_api_key_in_traceback(provider, caplog):
    sender, post, _ = provider
    post.side_effect = httpx.ReadTimeout("Error at https://api.mnotify.com/?key=private-test-api-key")
    with pytest.raises(SmsDeliveryError) as raised:
        sender.send_verification_otp(recipient="+233241234567", code="135790", expires_in_minutes=10)
    assert "private-test-api-key" not in ''.join(traceback.format_exception(raised.value))
    assert "private-test-api-key" not in caplog.text
    assert "135790" not in caplog.text
    assert post.call_count == 1
