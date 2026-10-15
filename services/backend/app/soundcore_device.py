"""Official D3200 SDK authentication; long-lived vendor key never reaches mobile."""
import hashlib
import hmac
import json
import time
import httpx
from .errors import AppError

SDK_VERSION = 'V1.3.01'
PRODUCT = 'D3200'
ORIGIN = 'https://speaker-api-ci.anker-in.com'

class DeviceAuthUnavailable(AppError):
    code = 'DEVICE_AUTH_UNAVAILABLE'
    http_status = 503


def configured(settings):
    return bool(settings.soundcore_app_id and settings.soundcore_app_key.get_secret_value())


def authenticate(settings, actor_id, installation, *, transport=None):
    if not configured(settings):
        raise DeviceAuthUnavailable('设备连接服务尚未配置，手机录音仍可使用。')
    secret = settings.soundcore_app_key.get_secret_value()
    device_id = 'rm_' + hmac.new(secret.encode(), (actor_id + ':' + installation).encode(), hashlib.sha256).hexdigest()[:32]
    body = {'app_id': settings.soundcore_app_id, 'app_key': secret, 'user_id': actor_id,
            'device_id': device_id, 'timestamp': int(time.time() * 1000)}
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False, transport=transport) as client:
            response = client.post(ORIGIN + '/v1/third_party_sdk/get_token', json=body,
                headers={'X-Product-Code': PRODUCT, 'X-Soundcore-SDK-Version': SDK_VERSION})
        response.raise_for_status()
        if len(response.content) > 65536: raise ValueError('oversized')
        result = response.json()
        if result.get('code') != 1: raise ValueError('vendor refusal')
        data = result['data']; license_data = data['license']
        if not isinstance(license_data, dict) or not isinstance(data['token'], str) or not data['token']:
            raise ValueError('invalid receipt')
        # The SDK verifies the signed license. Refuse a receipt for another user,
        # installation or app before exposing it to this authenticated caller.
        for key, expected in [('app_id', settings.soundcore_app_id), ('user_id', actor_id), ('device_id', device_id)]:
            if license_data.get(key) != expected: raise ValueError('license scope mismatch')
        expires = int(data['token_expire_time'])
        if expires <= time.time(): raise ValueError('expired')
        if not isinstance(data['license_signature'], str) or not data['license_signature']: raise ValueError('missing signature')
        return {'user_id': actor_id, 'device_id': device_id, 'token': data['token'],
                'license_json': json.dumps(license_data, ensure_ascii=False, separators=(',', ':')),
                'license_signature': data['license_signature'], 'token_expires_at': expires,
                'environment': 'development', 'sdk_version': SDK_VERSION, 'product_code': PRODUCT}
    except Exception:
        # Never include vendor response text, URL parameters or credentials.
        raise DeviceAuthUnavailable('录音豆认证暂未完成，请稍后重试。手机录音仍可使用。') from None
