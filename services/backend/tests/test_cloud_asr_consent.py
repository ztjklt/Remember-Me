import json
from contextlib import contextmanager

import httpx
import pytest
from sqlalchemy import select

from app.models import Episode, Job, Consent
from app.relay_asr import RelaySttProvider, cloud_policy
from app.seed import seed_development_data
from app.worker import ProcessingWorker


def setup_cloud(app, session, monkeypatch):
    own = seed_development_data(session, subject_name='云端测试', actor_name='本人')
    settings = app.state.settings
    settings.stt_backend = 'relay'
    settings.relay_asr_url = 'https://relay.example/v1/chat/completions'
    from pydantic import SecretStr
    settings.relay_asr_api_key = SecretStr('unit-test-key')
    sent = []
    def post(*a, **kw):
        sent.append(kw['json'])
        return httpx.Response(200, json={'model': 'route', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': '我沒有去過北京。'}}]})
    monkeypatch.setattr(httpx, 'post', post)
    return own, {'Authorization': 'Bearer ' + own.actor_token}, sent


def upload(client, own, headers, metadata=None):
    return client.post('/api/v1/episodes', headers=headers, data={
        'subject_id': own.subject_id, 'recording_consent_id': own.consent_id,
        'idempotency_key': 'cloud-test', 'source': 'IMPORT',
        'recorded_at': '2026-10-08T09:00:00+08:00', 'audio_ref': 'test.wav',
        'metadata': json.dumps(metadata or {})},
        files={'file': ('test.wav', b'ACTUAL-FICTIONAL-AUDIO', 'audio/wav')})


@pytest.mark.parametrize('metadata', [{}, {'cloud_asr_policy': 'old'},
    {'cloud_asr_receipt': {'policy': 'fabricated', 'actor_id': 'fake'}}])
def test_upload_cannot_treat_recording_consent_as_cloud_consent(app, client, session, monkeypatch, metadata):
    own, headers, sent = setup_cloud(app, session, monkeypatch)
    result = upload(client, own, headers, metadata)
    assert result.status_code == 422, result.text
    assert not sent
    assert not session.scalar(select(Episode))


class Gate:
    def __init__(self, after_wait=lambda: None):
        self.after_wait = after_wait

    @contextmanager
    def slot(self):
        self.after_wait()
        yield


def test_success_preserves_raw_asr_simplifies_review_and_waits(app, client, session, monkeypatch, tmp_path):
    own, headers, sent = setup_cloud(app, session, monkeypatch)
    settings = app.state.settings
    settings.relay_asr_state_dir = str(tmp_path)
    policy = cloud_policy(settings)
    result = upload(client, own, headers, {'cloud_asr_policy': policy,
        'cloud_asr_receipt': {'actor_id': 'forged'}})
    assert result.status_code == 201, result.text
    eid = result.json()['episode_id']
    worker = ProcessingWorker(app.state.database, app.state.object_store,
        RelaySttProvider(settings, gate=Gate()), app.state.ai_client)
    worker.run_once()
    session.expire_all()
    ep = session.get(Episode, eid)
    assert ep.stt_transcript == '我沒有去過北京。'
    assert ep.transcript == '我没有去过北京。'
    assert ep.capture_metadata['cloud_asr_receipt']['actor_id'] == own.actor_id
    assert ep.capture_metadata['asr_call']['request_model'] == 'codestral-2508'
    assert session.scalar(select(Job).where(Job.episode_id == eid)).state == 'waiting'
    assert len(sent) == 1


@pytest.mark.parametrize('why', ['old_queue', 'route_changed', 'revoked_during_wait'])
def test_queue_never_sends_without_current_cloud_permission(app, client, session, monkeypatch, tmp_path, why):
    own, headers, sent = setup_cloud(app, session, monkeypatch)
    settings = app.state.settings
    settings.relay_asr_state_dir = str(tmp_path)
    if why == 'old_queue':
        settings.stt_backend = 'fake'
    result = upload(client, own, headers, {'cloud_asr_policy': cloud_policy(settings)})
    assert result.status_code == 201
    eid = result.json()['episode_id']
    settings.stt_backend = 'relay'
    if why == 'route_changed':
        settings.relay_asr_model = 'mistral-code-fim-latest'
    def after_wait():
        if why == 'revoked_during_wait':
            with app.state.database.session() as db:
                db.get(Consent, own.consent_id).status = 'revoked'
                db.commit()
    worker = ProcessingWorker(app.state.database, app.state.object_store,
        RelaySttProvider(settings, gate=Gate(after_wait)), app.state.ai_client)
    worker.run_once()
    assert not sent
    session.expire_all()
    ep = session.get(Episode, eid)
    assert ep.status == 'failed'
    assert app.state.object_store.get(ep.audio_object_key) == b'ACTUAL-FICTIONAL-AUDIO'


def test_temporary_query_needs_explicit_cloud_permission(app, client, session, monkeypatch, tmp_path):
    own, headers, sent = setup_cloud(app, session, monkeypatch)
    app.state.settings.relay_asr_state_dir = str(tmp_path)
    app.state.stt_provider = RelaySttProvider(app.state.settings, gate=Gate())
    url = f'/api/v1/subjects/{own.subject_id}/twin/transcribe-query'
    result = client.post(url, headers=headers, content=b'test audio')
    assert result.status_code == 422
    assert not sent
    headers['X-Cloud-ASR-Policy'] = cloud_policy(app.state.settings)
    headers['Content-Type'] = 'audio/wav'
    result = client.post(url, headers=headers, content=b'test audio')
    assert result.status_code == 200, result.text
    assert result.json()['text'] == '我没有去过北京。'
    assert len(sent) == 1
