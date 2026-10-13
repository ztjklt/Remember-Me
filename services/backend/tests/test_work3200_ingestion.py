"""Hardware provenance reuses the ordinary consent/review boundary, not a bypass."""
import hashlib
import json

import pytest
from sqlalchemy import select

from app.models import Consent, Episode, Job
from app.seed import seed_development_data


def capture(client, own, *, mime='audio/wav', token=None, client_draft=False):
    audio = b'opaque-sdk-packets-not-a-decoded-wave'
    fields = {
        'subject_id': own.subject_id, 'recording_consent_id': own.consent_id,
        'source': 'WORK_3200', 'recorded_at': '2026-10-13T01:00:00Z',
        'audio_ref': 'device.opus', 'idempotency_key': 'hardware-ingestion',
    }
    if client_draft:
        fields['client_transcript'] = json.dumps({
            'text': '机器稿仍需本人核对。', 'audio_sha256': hashlib.sha256(audio).hexdigest(),
            'provider': 'groq', 'model': 'whisper-large-v3', 'audio_export_confirmed': True,
        })
    return client.post('/api/v1/episodes' + ('/client-transcribed' if client_draft else ''),
        headers={'Authorization': 'Bearer ' + (token or own.actor_token)}, data=fields,
        files={'file': ('device.opus', audio, mime)})


@pytest.mark.parametrize('client_draft', [False, True])
@pytest.mark.parametrize('mime', ['audio/opus', 'audio/opus; codecs=opus'])
def test_raw_work3200_opus_is_refused_without_queuing_or_relabelling_audio(client, session, mime, client_draft):
    own = seed_development_data(session, subject_name='本人', actor_name='本人')
    result = capture(client, own, mime=mime, client_draft=client_draft)
    assert result.status_code == 400, result.text
    assert result.json()['error_code'] == 'AUDIO_INVALID'
    assert session.scalar(select(Episode)) is None
    assert session.scalar(select(Job)) is None


@pytest.mark.parametrize('client_draft', [False, True])
def test_work3200_cannot_use_another_actor_or_revoked_consent(client, session, client_draft):
    own = seed_development_data(session, subject_name='本人', actor_name='本人')
    other = seed_development_data(session, subject_name='他人', actor_name='他人')
    assert capture(client, own, token=other.actor_token, client_draft=client_draft).status_code in (403, 404)
    session.get(Consent, own.consent_id).status = 'revoked'
    session.commit()
    assert capture(client, own, client_draft=client_draft).status_code in (403, 422)
    assert session.scalar(select(Episode)) is None
    assert session.scalar(select(Job)) is None
