"""Bounded JSON transport shared by explicitly validated provider adapters."""
import json
import math
import re
from time import monotonic
import httpx
from ..errors import (AIOutputInvalid, ProviderAuthenticationFailed,
    ProviderRateLimited, ProviderTimeout, ProviderUnavailable)


def reject_constant(value):
    raise ValueError('Nonfinite JSON number')


class JsonObjectChat:
    BASE_URL = None
    MODELS = frozenset()
    request_options = {}
    response_model_prefix = ''
    def __init__(self, *, api_key, model, base_url=None, timeout_seconds=40,
                 max_response_bytes=1_048_576, client=None):
        base_url = base_url or self.BASE_URL
        if base_url != self.BASE_URL or model not in self.MODELS or not api_key.strip():
            raise ValueError('Model requires its documented HTTPS endpoint, alias and credential')
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
        body.update(self.request_options)
        try:
            with self.client.stream('POST', self.base_url + '/chat/completions', json=body,
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    timeout=self.timeout_seconds, follow_redirects=False) as response:
                if response.status_code in {401, 403}:
                    raise ProviderAuthenticationFailed('Model credential rejected')
                if response.status_code in {408, 504}:
                    raise ProviderTimeout('Model model timed out')
                if response.status_code == 429:
                    try: delay = float(response.headers.get('Retry-After', '60'))
                    except ValueError: delay = 60
                    if not math.isfinite(delay): delay = 60
                    delay = max(1, min(delay, 3600))
                    self._blocked_until = monotonic() + delay
                    raise ProviderRateLimited(delay)
                if response.status_code >= 500:
                    raise ProviderUnavailable('Model model unavailable')
                if not response.is_success:
                    raise AIOutputInvalid('Model request rejected')
                chunks = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    if len(chunks) + len(chunk) > self.max_response_bytes:
                        raise AIOutputInvalid('Model response too large')
                    chunks.extend(chunk)
            envelope = json.loads(chunks, parse_constant=reject_constant)
            version = envelope['model']
            if (not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,128}', version)
                    or not version.startswith(self.response_model_prefix)):
                raise AIOutputInvalid('Model response model identity missing')
            choice = envelope['choices'][0]
            if choice.get('finish_reason') != 'stop' or choice['message'].get('refusal'):
                raise AIOutputInvalid('Model response incomplete or refused')
            result = json.loads(choice['message']['content'], parse_constant=reject_constant)
            if not isinstance(result, dict):
                raise AIOutputInvalid('Model structured output must be an object')
            return result, version
        except httpx.TimeoutException as exc:
            raise ProviderTimeout('Model model timed out') from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable('Model model connection failed') from exc
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError) as exc:
            raise AIOutputInvalid('Model returned malformed JSON') from exc

