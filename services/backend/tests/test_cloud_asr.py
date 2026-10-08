"""Relay wire tests are hermetic, not evidence of a live relay transcription."""
import base64
import json
from contextlib import contextmanager

import httpx
import pytest

from app.config import Settings
from app.errors import SttFailed, SttUnavailable
from app.relay_asr import RelaySttProvider, cloud_policy
from app.stt import build_stt_provider


class ImmediateGate:
    @contextmanager
    def slot(self):
        yield

    def defer(self, seconds):
        self.deferred = seconds


def configured(tmp_path, **changes):
    return Settings(_env_file=None, stt_backend='relay',
        relay_asr_url='https://relay.example/v1/chat/completions',
        relay_asr_api_key='only-a-unit-test-key',
        relay_asr_state_dir=str(tmp_path), **changes)


def response(content='我没有去过北京，也许明年去。', reason='stop'):
    return httpx.Response(200, json={'model': 'actual-reported-route', 'usage': {'total_tokens': 19},
        'choices': [{'finish_reason': reason, 'message': {'content': content}}]})


def test_actual_bytes_only_and_model_provenance(monkeypatch, tmp_path):
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        return response()
    monkeypatch.setattr(httpx, 'post', post)
    provider = RelaySttProvider(configured(tmp_path), gate=ImmediateGate())
    answer = provider.transcribe(b'ACTUAL-AUDIO', 'audio/wav')
    url, request = calls[0]
    assert url == 'https://relay.example/v1/chat/completions'
    assert request['follow_redirects'] is False
    body = request['json']
    assert body['model'] == 'codestral-2508'
    encoded = body['messages'][1]['content'][1]['audio_url']['url'].split(',')[1]
    assert base64.b64decode(encoded) == b'ACTUAL-AUDIO'
    assert answer.text == '我没有去过北京，也许明年去。'
    assert answer.backend == 'relay'
    assert answer.metadata['response_model'] == 'actual-reported-route'
    assert answer.metadata['request_model'] == 'codestral-2508'
    audit = (tmp_path / 'calls.jsonl').read_text()
    assert 'only-a-unit-test-key' not in audit and 'ACTUAL-AUDIO' not in audit
    assert answer.text not in audit
    assert json.loads(audit)['validation'] == 'transcript_received_unreviewed'


@pytest.mark.parametrize('content,reason', [('', 'stop'), ('不支持音频，请提供文字', 'stop'),
    ('I cannot transcribe audio files.', 'stop'), ('半段转写', 'length'), ('错误', 'content_filter')])
def test_refusal_empty_and_truncation_are_not_transcripts(monkeypatch, tmp_path, content, reason):
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: response(content, reason))
    provider = RelaySttProvider(configured(tmp_path), gate=ImmediateGate())
    with pytest.raises(SttFailed):
        provider.transcribe(b'audio', 'audio/wav')
    assert json.loads((tmp_path / 'calls.jsonl').read_text())['validation'] != 'transcript_received_unreviewed'


@pytest.mark.parametrize('status,error', [(401, SttFailed), (402, SttFailed),
    (400, SttFailed), (429, SttUnavailable), (503, SttUnavailable), (302, SttFailed)])
def test_error_one_request_no_fallback_or_body_leak(monkeypatch, tmp_path, status, error):
    calls = []
    def post(*args, **kwargs):
        calls.append(args)
        return httpx.Response(status, text='SECRET upstream body with audio and key')
    monkeypatch.setattr(httpx, 'post', post)
    provider = RelaySttProvider(configured(tmp_path), gate=ImmediateGate())
    with pytest.raises(error) as caught:
        provider.transcribe(b'audio', 'audio/wav')
    assert 'SECRET' not in str(caught.value)
    assert 'SECRET' not in (tmp_path / 'calls.jsonl').read_text()
    assert len(calls) == 1


def test_missing_configuration_never_uses_local_provider(tmp_path):
    settings = Settings(_env_file=None, stt_backend='relay', relay_asr_state_dir=str(tmp_path))
    provider = build_stt_provider(settings)
    assert isinstance(provider, RelaySttProvider)
    with pytest.raises(SttFailed, match='配置'):
        provider.transcribe(b'audio', 'audio/wav')


def test_policy_binds_destination_model_format_not_secret(tmp_path):
    original = configured(tmp_path)
    assert cloud_policy(original) == cloud_policy(original.model_copy(update={'relay_asr_api_key': 'rotated'}))
    for change in ({'relay_asr_model': 'mistral-code-fim-latest'},
                   {'relay_asr_url': 'https://other.example/v1/chat/completions'},
                   {'relay_asr_format': 'input_audio'}):
        assert cloud_policy(original) != cloud_policy(original.model_copy(update=change))


def test_authorization_is_rechecked_after_queue_wait(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: sent.append(True))
    def revoked():
        raise SttFailed('consent revoked')
    provider = RelaySttProvider(configured(tmp_path), gate=ImmediateGate())
    with pytest.raises(SttFailed, match='revoked'):
        provider.transcribe_authorized(b'audio', 'audio/wav', revoked)
    assert not sent


def test_serial_gate_survives_restart_and_429_does_not_shorten_cooldown(monkeypatch, tmp_path):
    import app.relay_asr as relay
    now = [1000.0]
    monkeypatch.setattr(relay.time, 'time', lambda: now[0])
    monkeypatch.setattr(relay.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    first = relay.SerialGate(tmp_path)
    with first.slot(): pass
    assert now[0] == 1000
    second = relay.SerialGate(tmp_path)
    with second.slot():
        assert now[0] == 1035
        second.defer(305)
    third = relay.SerialGate(tmp_path)
    with third.slot(): assert now[0] == 1340


def test_corrupt_gate_state_fails_closed(tmp_path):
    from app.relay_asr import SerialGate
    (tmp_path / 'next-request.json').write_text('broken')
    with pytest.raises(SttFailed, match='检查点'):
        with SerialGate(tmp_path).slot():
            pytest.fail('must not enter outbound request')
