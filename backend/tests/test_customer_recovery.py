import re
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models.email_otp_challenge import EmailOtpChallenge
from app.routes import auth


@pytest.fixture
def recovery_client(support_db, monkeypatch):
    session, customers, *_ = support_db
    customer = customers[0]
    customer.email = 'ama-boateng@example.com'
    customer.phone_number = '+233241234567'
    customer.phone_verified_at = datetime.now(UTC)
    customer.pin_hash = 'test-hash:123456'
    session.commit()
    hasher = Mock()
    hasher.hash.side_effect = lambda pin: f'test-hash:{pin}'
    hasher.verify.side_effect = lambda stored, supplied: stored == f'test-hash:{supplied}'
    monkeypatch.setattr(auth.Argon2PinHasher, 'from_settings', lambda settings: hasher)
    settings = Settings(
        _env_file=None,
        otp_hash_secret='a-secure-test-secret-that-is-at-least-32-characters',
        otp_resend_cooldown_seconds=60,
    )
    email_sender = Mock()
    sms_sender = Mock()
    router = Mock()
    router.get_hotspot_user.return_value = {'name': customer.username}
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_password_email_sender] = lambda: email_sender
    app.dependency_overrides[auth.get_password_sms_sender] = lambda: sms_sender
    app.dependency_overrides[auth.get_password_router_factory] = lambda: lambda router_id: router
    try:
        yield TestClient(app), session, customer, email_sender, sms_sender, router
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.parametrize('identifier', ['ama', '024 123 4567', '+233241234567', '233241234567'])
def test_sign_in_with_username_or_phone(recovery_client, identifier):
    client, *_ = recovery_client
    response = client.post('/api/auth/login', json={'username': identifier, 'pin': '123456'})
    assert response.status_code == 200, response.text
    assert response.json() == {'username': 'ama', 'redirect_to': '/account'}


def test_zero_prefixed_username_can_sign_in(recovery_client):
    client, session, customer, *_ = recovery_client
    customer.username = '0ama'
    session.commit()
    response = client.post('/api/auth/login', json={'username': '0ama', 'pin': '123456'})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('identifier', ['ama', '+233241234567'])
def test_locked_login_can_only_be_unlocked_with_valid_account_code(recovery_client, identifier):
    client, session, customer, email_sender, *_ = recovery_client
    for attempt in range(5):
        response = client.post('/api/auth/login', json={
            'username': 'ama' if attempt % 2 else '0241234567', 'pin': '999999',
        })
        assert response.status_code == (423 if attempt == 4 else 401)
    assert customer.locked_at is not None
    assert client.post('/api/auth/login', json={'username': identifier, 'pin': '123456'}).status_code == 423

    started = client.post('/api/auth/account-unlock/start', json={'username': identifier})
    assert started.status_code == 200, started.text
    code = email_sender.send_account_unlock_otp.call_args.kwargs['code']
    payload = {'challenge_id': started.json()['challenge_id'], 'username': identifier, 'code': code}
    assert client.post('/api/auth/account-unlock/complete', json={**payload, 'username': 'kwame'}).status_code == 400
    assert customer.locked_at is not None
    completed = client.post('/api/auth/account-unlock/complete', json=payload)
    assert completed.status_code == 200, completed.text
    session.refresh(customer)
    assert customer.locked_at is None
    assert customer.failed_login_attempts == 0
    assert client.post('/api/auth/account-unlock/complete', json=payload).status_code == 400
    assert client.post('/api/auth/login', json={'username': identifier, 'pin': '123456'}).status_code == 200


def test_unlock_is_unavailable_for_unlocked_account(recovery_client):
    client, _, _, email_sender, *_ = recovery_client
    assert client.post('/api/auth/account-unlock/start', json={'username': 'ama'}).status_code == 409
    email_sender.send_account_unlock_otp.assert_not_called()


@pytest.mark.parametrize('identifier', ['ama-boateng@example.com', '024 123 4567'])
def test_pin_reset_completes_by_email_or_verified_phone(recovery_client, identifier):
    client, _, customer, email_sender, sms_sender, router = recovery_client
    response = client.post('/api/auth/pin-reset/start', json={'email': identifier})
    assert response.status_code == 200, response.text
    sender = email_sender if '@' in identifier else sms_sender
    code = sender.send_pin_reset_otp.call_args.kwargs['code']
    payload = {'challenge_id': response.json()['challenge_id'], 'email': identifier,
               'code': code, 'new_pin': '654321', 'new_pin_confirmation': '654321'}
    assert client.post('/api/auth/pin-reset/complete', json={**payload, 'new_pin_confirmation': '111111'}).status_code == 422
    completed = client.post('/api/auth/pin-reset/complete', json=payload)
    assert completed.status_code == 200, completed.text
    router.change_hotspot_user_password.assert_called_once_with(customer.username, '654321')
    assert client.post('/api/auth/pin-reset/complete', json=payload).status_code == 400
    assert client.post('/api/auth/login', json={'username': identifier if '@' not in identifier else 'ama', 'pin': '654321'}).status_code == 200


@pytest.mark.parametrize('identifier', ['ama-boateng@example.com', '+233241234567'])
def test_username_recovery_completes_by_email_or_sms(recovery_client, identifier):
    client, _, _, email_sender, sms_sender, _ = recovery_client
    response = client.post('/api/auth/username-recovery/start', json={'email': identifier})
    assert response.status_code == 200, response.text
    code = (email_sender.send_username_recovery_otp.call_args.kwargs['code'] if '@' in identifier
            else re.search(r'\b[0-9]{6}\b', sms_sender.send.call_args.kwargs['message']).group())
    payload = {'challenge_id': response.json()['challenge_id'], 'email': identifier, 'code': code}
    completed = client.post('/api/auth/username-recovery/complete', json=payload)
    assert completed.status_code == 200, completed.text
    assert completed.json() == {'username': 'ama'}
    assert client.post('/api/auth/username-recovery/complete', json=payload).status_code == 400


@pytest.mark.parametrize('purpose', ['pin-reset', 'username-recovery'])
def test_unverified_phone_does_not_receive_recovery_codes(recovery_client, purpose):
    client, session, customer, email_sender, sms_sender, _ = recovery_client
    customer.phone_verified_at = None
    session.commit()
    response = client.post(f'/api/auth/{purpose}/start', json={'email': customer.phone_number})
    assert response.status_code == 200
    email_sender.send_pin_reset_otp.assert_not_called()
    email_sender.send_username_recovery_otp.assert_not_called()
    sms_sender.send.assert_not_called()
    sms_sender.send_pin_reset_otp.assert_not_called()


def test_reset_rejects_expired_code(recovery_client):
    client, session, customer, email_sender, *_ = recovery_client
    response = client.post('/api/auth/pin-reset/start', json={'email': customer.email})
    challenge = session.get(EmailOtpChallenge, uuid.UUID(response.json()['challenge_id']))
    challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    payload = {'challenge_id': str(challenge.id), 'email': customer.email,
               'code': email_sender.send_pin_reset_otp.call_args.kwargs['code'],
               'new_pin': '654321', 'new_pin_confirmation': '654321'}
    assert client.post('/api/auth/pin-reset/complete', json=payload).status_code == 400
    assert customer.pin_hash == 'test-hash:123456'
