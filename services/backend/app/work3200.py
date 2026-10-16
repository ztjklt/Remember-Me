"""Soundcore grant exchange. Business credentials never leave this server."""
import json
import time

import httpx

from .config import Settings
from .errors import AppError


class HardwareNotConfigured(AppError):
    code = 'HARDWARE_NOT_CONFIGURED'
    http_status = 503


class HardwareAuthorizationUnavailable(AppError):
    code = 'HARDWARE_AUTH_UNAVAILABLE'
    http_status = 502


def issue_grant(settings: Settings, user_id: str, device_id: str,
                *, transport: httpx.BaseTransport | None = None) -> dict:
    if not settings.work3200_app_id or not settings.work3200_app_key.get_secret_value():
        raise HardwareNotConfigured('录音豆授权服务尚未配置。')
    environment = settings.work3200_environment
    host = ('speaker-api-ci.anker-in.com' if environment == 'DEVELOPMENT'
            else 'speaker-api.anker-in.com')
    try:
        with httpx.Client(timeout=20, transport=transport, follow_redirects=False) as client:
            response = client.post(f'https://{host}/v1/third_party_sdk/get_token',
                headers={'X-Product-Code': 'D3200', 'X-Soundcore-SDK-Version': 'V1.3.02'},
                json={'app_id': settings.work3200_app_id,
                      'app_key': settings.work3200_app_key.get_secret_value(),
                      'user_id': user_id, 'device_id': device_id,
                      'timestamp': int(time.time() * 1000)})
            response.raise_for_status()
            body = response.json()
        if body.get('code') != 1:
            raise ValueError('vendor rejected request')
        data = body['data']
        license_data = data['license']
        if (license_data['app_id'] != settings.work3200_app_id
                or license_data['user_id'] != user_id
                or license_data['device_id'] != device_id):
            raise ValueError('grant identity mismatch')
        now = int(time.time())
        if (int(data['token_expire_time']) <= now
                or int(license_data['license_expire_time']) <= now):
            raise ValueError('expired grant')
        if not all(isinstance(data[k], str) and 0 < len(data[k]) < 32768
                   for k in ('token', 'license_signature')):
            raise ValueError('invalid grant')
        return {'version': 1, 'environment': environment, 'user_id': user_id,
                'device_id': device_id, 'token': data['token'],
                'token_expire_time': data['token_expire_time'],
                'license_json': json.dumps(license_data, separators=(',', ':'), ensure_ascii=False),
                'license_signature': data['license_signature']}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Upstream responses/exceptions can contain credentials. Never echo them.
        raise HardwareAuthorizationUnavailable('录音豆授权暂不可用，请稍后重试。') from None
