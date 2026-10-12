"""Anker event router transport; shared evidence protocols remain unchanged.

Endpoint and aliases come from the event's supplied integration document.
Live capabilities remain unverified until its credential passes authentication.
"""
import json
import math
import re
from time import monotonic

import httpx

from ..errors import (AIOutputInvalid, ProviderAuthenticationFailed,
    ProviderRateLimited, ProviderTimeout, ProviderUnavailable)
from .weixin import WeixinProvider, WeixinTwinProvider, WeixinCalibrationProvider

BASE_URL = 'https://ai-router-cn-pub.anker-in.com'
MODELS = frozenset('hackathon/v_model/' + name for name in
    ('qwen-max', 'glm-5.2', 'deepseek-v4-pro', 'deepseek-v4.1-flash', 'kimi-k3', 'nova-pro'))


def reject_constant(value):
    raise ValueError('Nonfinite JSON number')


class AnkerChat:
    def __init__(self, *, api_key, model, base_url=BASE_URL, timeout_seconds=40,
                 max_response_bytes=1_048_576, client=None):
        if base_url != BASE_URL or model not in MODELS or not api_key.strip():
            raise ValueError('Anker requires its documented HTTPS endpoint, alias and credential')
        self.api_key, self.model, self.base_url = api_key, model, base_url
        self.timeout_seconds, self.max_response_bytes = timeout_seconds, max_response_bytes
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout_seconds, trust_env=False)
        self._blocked_until = 0

    def close(self):
        if self._owns_client:
            self.client.close()

    def complete(self, system, payload):
        if monotonic() < self._blocked_until:
            raise ProviderRateLimited(self._blocked_until - monotonic())
        body = {'model': self.model, 'stream': False, 'max_tokens': 4096,
            'messages': [{'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'response_format': {'type': 'json_object'}}
        try:
            with self.client.stream('POST', BASE_URL + '/chat/completions', json=body,
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    timeout=self.timeout_seconds, follow_redirects=False) as response:
                if response.status_code in {401, 403}:
                    raise ProviderAuthenticationFailed('Anker credential rejected')
                if response.status_code in {408, 504}:
                    raise ProviderTimeout('Anker model timed out')
                if response.status_code == 429:
                    try: delay = float(response.headers.get('Retry-After', '60'))
                    except ValueError: delay = 60
                    if not math.isfinite(delay): delay = 60
                    delay = max(1, min(delay, 3600))
                    self._blocked_until = monotonic() + delay
                    raise ProviderRateLimited(delay)
                if response.status_code >= 500:
                    raise ProviderUnavailable('Anker model unavailable')
                if not response.is_success:
                    raise AIOutputInvalid('Anker request rejected')
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid('Anker response too large')
                    chunks.extend(chunk)
            envelope = json.loads(chunks, parse_constant=reject_constant)
            version = envelope['model']
            if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,128}', version):
                raise AIOutputInvalid('Anker response model identity missing')
            choice = envelope['choices'][0]
            if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                raise AIOutputInvalid('Anker response incomplete or refused')
            result = json.loads(choice['message']['content'], parse_constant=reject_constant)
            if not isinstance(result, dict):
                raise AIOutputInvalid('Anker structured output must be an object')
            return result, version
        except httpx.TimeoutException as exc:
            raise ProviderTimeout('Anker model timed out') from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable('Anker model connection failed') from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as exc:
            raise AIOutputInvalid('Anker returned malformed JSON') from exc


class AnkerMemoryProvider(AnkerChat):
    # Reuse locally validated source-handle selection rather than changing Contract.
    generate = WeixinProvider.generate
    response_model_version = staticmethod(WeixinProvider.response_model_version)


class AnkerTwinProvider(AnkerChat):
    answer = WeixinTwinProvider.answer
    review_answer = WeixinTwinProvider.review_answer

    def __init__(self, *, focus_hints=False, verify_answers=True,
                 structured_answers=False, quote_answers=False, **kwargs):
        super().__init__(**kwargs)
        self.focus_hints, self.verify_answers = focus_hints, verify_answers
        self.structured_answers, self.quote_answers = structured_answers, quote_answers


class AnkerCalibrationProvider(AnkerChat):
    compare = WeixinCalibrationProvider.compare
