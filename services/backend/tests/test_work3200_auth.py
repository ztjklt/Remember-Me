"""The recording-device broker authenticates accounts before issuing vendor grants."""
from app.seed import seed_development_data
import json
import time
import httpx
import pytest
from pydantic import SecretStr
from app.work3200 import issue_grant, HardwareAuthorizationUnavailable

PATH = '/api/v1/hardware/work3200/credentials'
DEVICE = 'rm-install-12345678-1234-4321-9876-123456789012'


def test_device_credentials_require_login(client):
    response = client.post(PATH, json={'device_id': DEVICE})
    assert response.status_code == 401


def test_missing_vendor_configuration_is_explicit(client, session):
    own = seed_development_data(session, subject_name='本人', actor_name='本人')
    response = client.post(PATH, headers={'Authorization': 'Bearer ' + own.actor_token},
                           json={'device_id': DEVICE})
    assert response.status_code == 503
    assert response.json()['error_code'] == 'HARDWARE_NOT_CONFIGURED'


def test_client_cannot_choose_another_vendor_user(client, session):
    own = seed_development_data(session, subject_name='本人', actor_name='本人')
    response = client.post(PATH, headers={'Authorization': 'Bearer ' + own.actor_token},
                           json={'device_id': DEVICE, 'user_id': 'another-person'})
    assert response.status_code == 422


def vendor_response():
    return {'code': 1, 'data': {'token': 'temporary-token',
            'token_expire_time': int(time.time()) + 600,
            'license': {'app_id': 'test-app', 'user_id': 'actor', 'device_id': DEVICE,
                        'license_expire_time': int(time.time()) + 600},
            'license_signature': 'signed-license'}}


def test_broker_uses_vendor_environment_and_returns_only_scoped_grant(settings):
    settings.work3200_app_id = 'test-app'
    settings.work3200_app_key = SecretStr('server-only-secret')

    def handle(request):
        assert request.url.host == 'speaker-api-ci.anker-in.com'
        assert request.headers['X-Product-Code'] == 'D3200'
        assert request.headers['X-Soundcore-SDK-Version'] == 'V1.3.02'
        payload = json.loads(request.content)
        assert payload['app_key'] == 'server-only-secret'
        assert payload['user_id'] == 'actor'
        assert payload['device_id'] == DEVICE
        return httpx.Response(200, json=vendor_response())

    grant = issue_grant(settings, 'actor', DEVICE, transport=httpx.MockTransport(handle))
    assert grant['environment'] == 'DEVELOPMENT'
    assert json.loads(grant['license_json'])['device_id'] == DEVICE
    assert 'server-only-secret' not in json.dumps(grant)


@pytest.mark.parametrize('fault', ['identity', 'expired', 'code', 'redirect'])
def test_invalid_upstream_grants_fail_without_echoing_secrets(settings, fault):
    settings.work3200_app_id = 'test-app'
    settings.work3200_app_key = SecretStr('server-only-secret')
    data = vendor_response()
    if fault == 'identity':
        data['data']['license']['user_id'] = 'another-actor'
    elif fault == 'expired':
        data['data']['token_expire_time'] = 1
    elif fault == 'code':
        data['code'] = 8001
        data['message'] = 'server-only-secret'
    status = 302 if fault == 'redirect' else 200
    with pytest.raises(HardwareAuthorizationUnavailable) as error:
        issue_grant(settings, 'actor', DEVICE, transport=httpx.MockTransport(
            lambda request: httpx.Response(status, json=data, headers={'Location': 'https://untrusted.invalid'})))
    assert 'server-only-secret' not in str(error.value)
