"""Client ASR must not bypass review, provenance, audio binding or ownership."""
import hashlib
import json

import pytest
from sqlalchemy import select

from app.config import Settings
from app.errors import SttFailed
from app.models import Episode, Job, Consent
from app.seed import seed_development_data
from app.stt import build_stt_provider
from app.worker import ProcessingWorker


AUDIO = b'fictional-audio-unit-test-not-a-real-model-result'
RAW = '我沒有去過北京。'


def seed(session):
    return seed_development_data(session, subject_name='客户端测试', actor_name='本人')


def capture(client, own, payload=None, *, key='client-asr', audio=AUDIO, route='client-transcribed', metadata=None):
    data = {'subject_id': own.subject_id, 'recording_consent_id': own.consent_id,
            'idempotency_key': key, 'source': 'IMPORT', 'recorded_at': '2026-10-08T09:00:00+08:00',
            'audio_ref': 'fiction.wav', 'metadata': json.dumps(metadata or {})}
    if payload is None:
        payload = {'text': RAW, 'audio_sha256': hashlib.sha256(audio).hexdigest(),
                   'provider': 'groq', 'model': 'whisper-large-v3', 'audio_export_confirmed': True}
    if route:
        data['client_transcript'] = json.dumps(payload)
    return client.post('/api/v1/episodes' + ('/' + route if route else ''),
        headers={'Authorization': 'Bearer ' + own.actor_token}, data=data,
        files={'file': ('fiction.wav', audio, 'audio/wav')})


class NoServerASR:
    def transcribe(self, *args):
        raise AssertionError('Server ASR must never run for client transcripts')


def test_client_asr_is_saved_and_waits_for_review_then_reuses_pipeline(app, client, session):
    own = seed_development_data(session, subject_name='客户端样本', actor_name='本人')
    app.state.settings.stt_backend = 'groq'  # This path needs no server ASR key.
    result = capture(client, own, metadata={'cloud_asr_receipt': {'actor_id': 'forged'}})
    assert result.status_code == 201, result.text
    eid = result.json()['episode_id']
    ep = session.get(Episode, eid)
    job = session.scalar(select(Job).where(Job.episode_id == eid))
    assert ep.stt_transcript == RAW and ep.transcript == '我没有去过北京。'
    assert ep.stt_backend == 'client' and ep.stt_model_version == 'client-reported/groq/whisper-large-v3'
    assert ep.transcript_reviewed_at is None
    assert (job.stage, job.state) == ('extract', 'waiting')
    assert 'cloud_asr_receipt' not in ep.capture_metadata
    assert ep.capture_metadata['client_asr_receipt']['actor_id'] == own.actor_id
    assert ep.capture_metadata['client_asr_receipt']['verification'] == 'client_reported'
    worker = ProcessingWorker(app.state.database, app.state.object_store, NoServerASR(), app.state.ai_client)
    assert worker.run_once() is None
    headers = {'Authorization': 'Bearer ' + own.actor_token}
    review = client.get(f'/api/v1/episodes/{eid}/transcript-review', headers=headers).json()
    assert review['state'] == 'reviewing'
    audio = client.get(f'/api/v1/episodes/{eid}/audio', headers=headers)
    assert audio.status_code == 200 and audio.content == AUDIO
    submitted = client.patch(f'/api/v1/episodes/{eid}/transcript-review', headers=headers,
        json={'transcript': '我没有去过北京，也没去过上海。'})
    assert submitted.status_code == 200
    worker.run_once(); worker.run_once()
    session.expire_all()
    assert session.get(Episode, eid).stt_transcript == RAW
    assert session.get(Episode, eid).transcript == '我没有去过北京，也没去过上海。'
    assert client.get(f'/api/v1/episodes/{eid}/result', headers=headers).status_code == 200


@pytest.mark.parametrize('changes', [
    {'audio_sha256': '0'*64}, {'text': '   '}, {'text': 'a'*100001},
    {'audio_export_confirmed': False}, {'model': 'unknown'}, {'confirmed': True},
])
def test_invalid_client_drafts_cannot_create_or_queue_a_story(app, client, session, changes):
    own = seed(session)
    payload = {'text': RAW, 'audio_sha256': hashlib.sha256(AUDIO).hexdigest(),
               'provider': 'groq', 'model': 'whisper-large-v3', 'audio_export_confirmed': True, **changes}
    result = capture(client, own, payload)
    assert result.status_code == 422, result.text
    assert session.scalar(select(Episode)) is None
    assert session.scalar(select(Job)) is None


def test_client_capture_replay_cannot_change_raw_draft_or_turn_into_server_asr(app, client, session):
    own = seed(session)
    first = capture(client, own)
    assert first.status_code == 201, first.text
    replay = capture(client, own)
    assert replay.status_code == 200 and replay.json() == first.json()
    payload = {'text': '另一份稿子', 'audio_sha256': hashlib.sha256(AUDIO).hexdigest(),
               'provider': 'groq', 'model': 'whisper-large-v3', 'audio_export_confirmed': True}
    assert capture(client, own, payload).status_code == 409
    assert capture(client, own, route='').status_code == 409
    assert len(list(session.scalars(select(Episode)))) == 1


def test_client_asr_never_acquires_someone_elses_space_or_revoked_consent(app, client, session):
    from dataclasses import replace
    own = seed(session)
    other = seed_development_data(session, subject_name='其他人', actor_name='读者')
    forged = replace(own, actor_token=other.actor_token)
    assert capture(client, forged).status_code in (403, 404)
    session.get(Consent, own.consent_id).status = 'revoked'; session.commit()
    assert capture(client, own).status_code in (403, 422)
    assert session.scalar(select(Episode)) is None


def test_client_only_mode_blocks_old_capture_without_fake_or_network(app, client, session):
    settings = Settings(_env_file=None, environment='staging', stt_backend='client', ai_backend='http')
    provider = build_stt_provider(settings)
    with pytest.raises(SttFailed):
        provider.transcribe(AUDIO, 'audio/wav')
    own = seed(session)
    app.state.settings.stt_backend = 'client'
    blocked = capture(client, own, route='')
    assert blocked.status_code == 422
    assert session.scalar(select(Episode)) is None
    assert capture(client, own).status_code == 201


@pytest.mark.parametrize('old_metadata', [None, 'arbitrary old note', [], {'fingerprint':'not-reserved-before-upgrade'}])
def test_legacy_metadata_does_not_break_existing_audio_replays(app, client, session, old_metadata):
    own=seed(session)
    first=capture(client,own,route='')
    assert first.status_code==201
    ep=session.get(Episode,first.json()['episode_id'])
    ep.capture_metadata={'client_asr_receipt':old_metadata};session.commit()
    replay=capture(client,own,route='')
    assert replay.status_code==200 and replay.json()==first.json()
