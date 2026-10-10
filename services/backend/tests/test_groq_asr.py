"""Hermetic contract/consent checks; live evidence is recorded separately."""
import json
from contextlib import contextmanager

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.errors import SttFailed, SttUnavailable
from app.groq_asr import GroqSttProvider, ENDPOINT, cloud_policy
from app.models import Episode, Job, Consent
from app.stt import build_stt_provider
from app.worker import ProcessingWorker
from test_cloud_asr_consent import setup_cloud, upload, Gate


def provider(tmp_path, monkeypatch):
    monkeypatch.setattr('app.groq_asr.compact_audio', lambda raw: b'ACTUAL-MP3')
    settings = Settings(_env_file=None, stt_backend='groq', groq_api_key='unit-secret',
                        groq_asr_state_dir=str(tmp_path))
    return GroqSttProvider(settings, gate=Gate())


def test_real_bytes_without_author_text_and_honest_provenance(tmp_path, monkeypatch):
    sent = []
    def post(url, **kw):
        sent.append((url, kw))
        return httpx.Response(200, json={'text': '我没有去过北京。', 'duration': 3.2, 'segments': []})
    monkeypatch.setattr(httpx, 'post', post)
    p = provider(tmp_path, monkeypatch)
    result = p.transcribe(b'ORIGINAL', 'audio/wav')
    url, request = sent[0]
    assert url == ENDPOINT and request['follow_redirects'] is False
    assert request['trust_env'] is True
    assert request['files']['file'] == ('recording.mp3', b'ACTUAL-MP3', 'audio/mpeg')
    assert request['data'] == {'model': 'whisper-large-v3', 'language': 'zh',
                               'response_format': 'verbose_json', 'temperature': '0'}
    assert result.model_version == 'groq/whisper-large-v3'
    assert result.metadata['response_model'] is None
    audit = (tmp_path / 'calls.jsonl').read_text()
    assert 'unit-secret' not in audit and result.text not in audit


@pytest.mark.parametrize('status,error', [(401, SttFailed), (403, SttFailed),
    (400, SttFailed), (429, SttUnavailable), (503, SttUnavailable), (302, SttFailed)])
def test_failures_never_retry_or_leak_response(tmp_path, monkeypatch, status, error):
    calls = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: (calls.append(True), httpx.Response(status, text='PRIVATE'))[1])
    p = provider(tmp_path, monkeypatch)
    p.gate.defer = lambda _: None
    with pytest.raises(error): p.transcribe(b'audio', 'audio/wav')
    assert len(calls) == 1
    assert 'PRIVATE' not in (tmp_path / 'calls.jsonl').read_text()


@pytest.mark.parametrize('body', [{'text': ''}, {'text': 12}, {}, ['not-an-object']])
def test_invalid_output_cannot_succeed(tmp_path, monkeypatch, body):
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: httpx.Response(200, json=body))
    with pytest.raises(SttFailed): provider(tmp_path, monkeypatch).transcribe(b'audio', 'audio/wav')


@pytest.mark.parametrize('mode', ['success', 'revoked', 'old_policy'])
def test_product_consent_review_and_cutover(app, client, session, monkeypatch, tmp_path, mode):
    own, headers, _ = setup_cloud(app, session, monkeypatch)
    settings = app.state.settings
    from app.relay_asr import cloud_policy as relay_policy
    old_policy = relay_policy(settings)
    if mode != 'old_policy': settings.stt_backend = 'groq'
    settings.groq_api_key = SecretStr('test-key')
    settings.groq_asr_state_dir = str(tmp_path)
    result = upload(client, own, headers, {'cloud_asr_policy': old_policy if mode == 'old_policy' else cloud_policy(settings)})
    assert result.status_code == 201
    eid = result.json()['episode_id']
    settings.stt_backend = 'groq'
    sent = []
    monkeypatch.setattr('app.groq_asr.compact_audio', lambda raw: b'mp3')
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: (sent.append(True), httpx.Response(200, json={'text': '我沒有去過北京。'}))[1])
    def after_wait():
        if mode == 'revoked':
            with app.state.database.session() as db:
                db.get(Consent, own.consent_id).status = 'revoked'; db.commit()
    p = GroqSttProvider(settings, gate=Gate(after_wait))
    ProcessingWorker(app.state.database, app.state.object_store, p, app.state.ai_client).run_once()
    session.expire_all()
    ep = session.get(Episode, eid)
    if mode == 'success':
        assert sent == [True]
        assert ep.stt_transcript == '我沒有去過北京。' and ep.transcript == '我没有去过北京。'
        assert ep.stt_backend == 'groq'
        assert session.scalar(select(Job).where(Job.episode_id == eid)).state == 'waiting'
    else:
        assert not sent and ep.status == 'failed'


def test_missing_or_old_policy_rejected_before_upload(app, client, session, monkeypatch):
    own, headers, _ = setup_cloud(app, session, monkeypatch)
    from app.relay_asr import cloud_policy as relay_policy
    old = relay_policy(app.state.settings)
    app.state.settings.stt_backend = 'groq'
    app.state.settings.groq_api_key = SecretStr('test')
    for policy in ['', old]:
        assert upload(client, own, headers, {'cloud_asr_policy': policy}).status_code == 422
    caps = client.get('/api/v1/workbench/capabilities', headers=headers).json()
    assert caps['stt_model'] == 'whisper-large-v3' and caps['stt_host'] == 'api.groq.com'
    assert caps['stt_processing'] == 'cloud'


def test_factory_and_launcher_preserve_groq(tmp_path):
    from run_workbench import prepare_runtime
    settings = Settings(_env_file=None, stt_backend='groq', groq_asr_state_dir=str(tmp_path))
    assert isinstance(build_stt_provider(settings), GroqSttProvider)
    with pytest.raises(SttFailed): build_stt_provider(settings).transcribe(b'audio', 'audio/wav')
    env, ai, commands = prepare_runtime({'REMEMBER_STT_BACKEND': 'groq'}, {})
    assert env['REMEMBER_STT_BACKEND'] == 'groq'
    assert not any('app.local_stt:app' in c[-1] for c in commands)
