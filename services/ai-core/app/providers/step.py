"""Opt-in Step voice source-selection adapter. Not wired into production defaults."""
import asyncio
import hashlib
import json
import logging
import math
from contextlib import contextmanager, asynccontextmanager
from contextvars import ContextVar, copy_context
from time import perf_counter

import httpx

from ..cancellation import check_cancelled, cancellable
from ..errors import AIOutputInvalid, ProviderAuthenticationFailed, ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from ..telemetry import quote_trace_id
from .point_stream import Points, unique_object
from .transport_trace import TransportTrace
from .voice_race import bounded_retry

_scope = ContextVar('step_voice_scope', default=None)
logger = logging.getLogger('remember_me.ai_core')
MODEL = 'step-3.5-flash-2603'
ENDPOINT = 'https://api.stepfun.com/v1/chat/completions'


class StepVoiceChat:
    model = MODEL
    supports_stream_validation = True

    def __init__(self, *, api_key, transport=None):
        self.api_key = api_key
        self.transport = transport
        self._blocked_until = 0.0

    def _client(self):
        return httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=45,
            transport=self.transport,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2, keepalive_expiry=5))

    def close(self):
        # All clients belong to a bounded request/scope, never a background worker.
        pass

    @contextmanager
    def transport_scope(self, *, timeout_seconds=8, retry_after_seconds=0):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('Invalid Step request deadline')
        if not math.isfinite(retry_after_seconds) or retry_after_seconds < 0:
            raise ValueError('Invalid Step retry delay')
        with asyncio.Runner() as runner:
            client = self._client()
            state = dict(owner=self, runner=runner, client=client,
                         deadline=perf_counter()+timeout_seconds, delay=retry_after_seconds, remaining=2)
            token = _scope.set(state)
            try: yield
            finally:
                runner.run(client.aclose())
                _scope.reset(token)

    @property
    def stream_retry_managed(self):
        state = _scope.get()
        return bool(state and state['owner'] is self and state['delay'] > 0)

    @asynccontextmanager
    async def _request_client(self):
        state = _scope.get()
        if state and state['owner'] is self:
            yield state['client']
        else:
            async with self._client() as client: yield client

    def _status(self, response, record):
        record['status'] = response.status_code
        if response.status_code in (401, 403):
            raise ProviderAuthenticationFailed('Step authentication failed')
        if response.status_code == 429:
            try: delay = float(response.headers.get('Retry-After', '60'))
            except ValueError: delay = 60
            delay = max(1, min(delay, 3600)) if math.isfinite(delay) else 60
            self._blocked_until = perf_counter()+delay
            record['retry_after_seconds'] = delay
            raise ProviderRateLimited(delay)
        if response.status_code in (408, 504): raise ProviderTimeout('Step timed out')
        if response.status_code >= 500: raise ProviderUnavailable('Step temporarily unavailable')
        if not response.is_success: raise AIOutputInvalid('Step rejected request')

    def complete_stream(self, system, payload, *, on_point, timeout_seconds=None, validate_result=None):
        check_cancelled()
        start = perf_counter(); state = _scope.get()
        if not state or state['owner'] is not self: state = None
        budget = timeout_seconds if timeout_seconds is not None else 45
        if state: budget = min(budget, state['deadline']-perf_counter())
        managed = self.stream_retry_managed
        record = dict(event='step_chat_stream', requested_model=MODEL, reasoning_effort='low',
                      max_tokens=2048, prompt_sha256=hashlib.sha256(system.encode()).hexdigest(), attempts=[])
        if quote_trace_id.get(): record['trace_id'] = quote_trace_id.get()
        stable = ('recordings', 'confirmed_understanding', 'understandings', 'examples', 'contributions', 'response_schema')
        ordered = {k: payload[k] for k in stable if k in payload}
        ordered.update({k: v for k, v in payload.items() if k not in ordered})
        body = dict(model=MODEL, reasoning_effort='low', stream=True, max_tokens=2048,
                    response_format={'type': 'json_object'}, messages=[
                        {'role': 'system', 'content': system},
                        {'role': 'user', 'content': json.dumps(ordered, ensure_ascii=False, separators=(',', ':'))}])

        async def attempt(number=1):
            check_cancelled()
            if state:
                if state['remaining'] <= 0: raise ProviderTimeout('Step request budget exhausted')
                state['remaining'] -= 1
            began = perf_counter()
            row = dict(number=number, start_ms=round((began-start)*1000, 3))
            record['attempts'].append(row)
            trace = TransportTrace(row, began)
            parser = Points(); data = []; stopped = done = False; identity = None; size = 0
            try:
                async with self._request_client() as client:
                    async with client.stream('POST', ENDPOINT, json=body,
                            headers={'Authorization': 'Bearer '+self.api_key}, extensions={'trace': trace}) as response:
                        trace.headers(); self._status(response, row)
                        async for line in response.aiter_lines():
                            check_cancelled(); size += len(line.encode('utf8'))
                            if size > 1_048_576: raise ValueError('stream too large')
                            if line.startswith('data:'): data.append(line[5:].lstrip()); continue
                            if line or not data: continue
                            raw = '\n'.join(data); data = []
                            if done: raise ValueError('data after DONE')
                            if raw == '[DONE]': done = True; continue
                            event = json.loads(raw, object_pairs_hook=unique_object)
                            if not isinstance(event, dict) or event.get('error'): raise ValueError('stream error')
                            if event.get('model') is not None:
                                model = event['model']
                                if model != MODEL: raise ValueError('unexpected Step model')
                                identity = model
                            usage = event.get('usage')
                            if isinstance(usage, dict):
                                row['usage'] = {k: v for k, v in usage.items() if k in (
                                    'prompt_tokens', 'completion_tokens', 'total_tokens') and type(v) is int}
                                for field, child in [('prompt_tokens_details', 'cached_tokens'),
                                                     ('completion_tokens_details', 'reasoning_tokens')]:
                                    value = usage.get(field, {})
                                    if isinstance(value, dict) and type(value.get(child)) is int:
                                        row['usage'][child] = value[child]
                            for choice in event.get('choices', []):
                                if choice.get('index', 0) != 0: raise ValueError('multiple choices')
                                delta = choice.get('delta') or {}
                                if delta.get('refusal') or delta.get('tool_calls'): raise ValueError('refusal or tool call')
                                reasoning = delta.get('reasoning_content') or delta.get('reasoning')
                                if reasoning:
                                    if not isinstance(reasoning, str): raise ValueError('invalid reasoning')
                                    row.setdefault('first_reasoning_ms', round((perf_counter()-began)*1000, 3))
                                    row['reasoning_chars'] = row.get('reasoning_chars', 0)+len(reasoning)
                                content = delta.get('content')
                                if content:
                                    if stopped or not isinstance(content, str) or identity is None: raise ValueError('invalid content')
                                    row.setdefault('first_content_ms', round((perf_counter()-began)*1000, 3))
                                    for _ in parser.feed(content):
                                        row.setdefault('first_point_ms', round((perf_counter()-began)*1000, 3))
                                finish = choice.get('finish_reason')
                                if finish is not None:
                                    row['finish_reason'] = finish if finish in ('stop', 'length', 'tool_calls') else 'other'
                                    if finish != 'stop': raise ValueError('incomplete completion')
                                    stopped = True
                        if not done or not stopped or data or identity is None: raise ValueError('truncated stream')
                        result = parser.finish()
                        if validate_result is not None: validate_result(result, identity)
                        row['json_object_parsed'] = True
                        record.update(winner=number, response_model=identity, json_object_parsed=True)
                        for k in ('first_reasoning_ms', 'first_content_ms', 'first_point_ms'):
                            if k in row: record[k] = round(row['start_ms']+row[k], 3)
                        if 'usage' in row: record['usage'] = row['usage']
                        return result, identity
            except (httpx.TimeoutException, TimeoutError): trace.timeout(); raise
            except asyncio.CancelledError:
                row.update(cancelled=True, cancelled_phase=trace.active); raise
            finally: row['duration_ms'] = round((perf_counter()-began)*1000, 3)

        async def run():
            async with asyncio.timeout(budget):
                return await cancellable(bounded_retry(attempt, delay=state['delay'], timeout=budget)
                                         if managed else attempt())
        try:
            if start < self._blocked_until: raise ProviderRateLimited(self._blocked_until-start)
            if not math.isfinite(budget) or budget <= 0: raise ProviderTimeout('Step request budget exhausted')
            result = state['runner'].run(run(), context=copy_context()) if state else asyncio.run(run())
            check_cancelled()
            # Same as the bounded Weixin path: only a fully validated winner escapes.
            for point in result[0]['points']: on_point(point, result[1])
            return result
        except (httpx.TimeoutException, TimeoutError) as exc: raise ProviderTimeout('Step timed out') from exc
        except httpx.TransportError as exc: raise ProviderUnavailable('Step transport failed') from exc
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError) as exc:
            raise AIOutputInvalid('Step malformed stream') from exc
        finally:
            record['duration_ms'] = round((perf_counter()-start)*1000, 3)
            logger.info(json.dumps(record, ensure_ascii=True))
