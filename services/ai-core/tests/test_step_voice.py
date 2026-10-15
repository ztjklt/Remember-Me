import asyncio
import json
import threading
import time

import httpx
import pytest

from app.cancellation import cancelled_request
from app.errors import AIOutputInvalid, ProviderAuthenticationFailed, ProviderRateLimited, ProviderTimeout, ProviderUnavailable
from app.providers.step import StepVoiceChat


SELECTION = {'points': [{'known': True, 'source_ids': ['s1']}]}


def sse(*, finish='stop', done=True, reasoning='private thought'):
    def event(delta, reason=None):
        return 'data: ' + json.dumps({'model': 'step-3.5-flash-2603',
            'choices': [{'index': 0, 'delta': delta, 'finish_reason': reason}]}) + '\n\n'
    text = event({'reasoning_content': reasoning})
    text += event({'content': json.dumps(SELECTION)}) + event({}, finish)
    return (text + ('data: [DONE]\n\n' if done else '')).encode()


def chat(handler):
    return StepVoiceChat(api_key='private-test-key', transport=httpx.MockTransport(handler))


def test_low_mode_and_reasoning_never_enter_answer(caplog):
    def handler(request):
        body = json.loads(request.content)
        assert request.url == 'https://api.stepfun.com/v1/chat/completions'
        assert body['reasoning_effort'] == 'low' and body['stream'] is True
        assert body['max_tokens'] == 2048
        assert body['response_format'] == {'type': 'json_object'}
        return httpx.Response(200, content=sse())
    points = []
    result, model = chat(handler).complete_stream('system', {'recordings': ['intact']}, on_point=lambda p, _: points.append(p))
    assert result == SELECTION and points == SELECTION['points']
    assert model == 'step-3.5-flash-2603'
    assert 'private-test-key' not in caplog.text and 'private thought' not in caplog.text


@pytest.mark.parametrize('kwargs', [{'finish': 'length'}, {'done': False}])
def test_incomplete_never_delivers_points(kwargs):
    points = []
    with pytest.raises(AIOutputInvalid):
        chat(lambda _: httpx.Response(200, content=sse(**kwargs))).complete_stream(
            'system', {}, on_point=lambda *p: points.append(p))
    assert not points


def test_source_validator_runs_before_any_delivery():
    points = []
    def invalid(*_): raise AIOutputInvalid('unknown source')
    with pytest.raises(AIOutputInvalid):
        chat(lambda _: httpx.Response(200, content=sse())).complete_stream('system', {},
            on_point=lambda *p: points.append(p), validate_result=invalid)
    assert not points


@pytest.mark.parametrize('status,error', [(401, ProviderAuthenticationFailed), (429, ProviderRateLimited)])
def test_auth_and_quota_are_not_retried(status, error):
    calls = []
    def handler(_):
        calls.append(1)
        return httpx.Response(status, headers={'Retry-After': '10'}, text='private upstream body')
    provider = chat(handler)
    with pytest.raises(error), provider.transport_scope(timeout_seconds=.3, retry_after_seconds=.1):
        provider.complete_stream('system', {}, on_point=lambda *_: None)
    assert len(calls) == 1


def test_shared_deadline_includes_retry_and_closes_requests():
    active = []; calls = []
    async def handler(_):
        active.append(1); calls.append(1)
        try: await asyncio.sleep(2)
        finally: active.pop()
    provider = chat(handler); start = time.perf_counter()
    with pytest.raises(ProviderTimeout), provider.transport_scope(timeout_seconds=.12, retry_after_seconds=.04):
        provider.complete_stream('system', {}, on_point=lambda *_: None)
    assert time.perf_counter()-start < .5 and len(calls) == 2 and not active


def test_cancelled_caller_does_not_receive_late_answer():
    event = threading.Event(); token = cancelled_request.set(event)
    async def handler(_):
        event.set()
        await asyncio.sleep(2)
        return httpx.Response(200, content=sse())
    try:
        with pytest.raises(ProviderUnavailable):
            chat(handler).complete_stream('system', {}, on_point=lambda *_: pytest.fail('late result'))
    finally: cancelled_request.reset(token)
