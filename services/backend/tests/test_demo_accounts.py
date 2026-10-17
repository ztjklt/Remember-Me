"""Demo is a login mechanism, never an ACL shortcut."""
import pytest
from sqlalchemy import select
from app.models import DeviceCredential, Subject, utcnow, as_utc
from test_agent_workbench import setup_pair
from test_twin_voice import _record


def configured(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    settings = app.state.settings
    settings.demo_accounts_enabled = True
    settings.demo_owner_actor_id = owner.actor_id
    settings.demo_relative_actor_id = reader.actor_id
    settings.demo_subject_id = owner.subject_id
    return owner, reader, oh, rh, ep, cloud


def enter(client, role):
    result = client.post('/api/v1/accounts/demo-session', json={'role': role})
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    return result.json(), {'Authorization': 'Bearer ' + result.json()['actor_token']}


def test_default_closed_and_cannot_choose_arbitrary_identity(client):
    assert client.post('/api/v1/accounts/demo-session', json={'role': 'owner'}).status_code == 404
    assert client.post('/api/v1/accounts/demo-session', json={'role': 'admin'}).status_code == 422
    assert client.post('/api/v1/accounts/demo-session', json={'role': 'owner', 'actor_id': 'someone'}).status_code == 422


@pytest.mark.parametrize('bad', ['same_actor', 'wrong_owner', 'extra_space', 'missing_actor'])
def test_misconfiguration_fails_closed(app, client, session, bad):
    owner, reader, *_ = configured(app, client, session)
    settings = app.state.settings
    if bad == 'same_actor': settings.demo_relative_actor_id = owner.actor_id
    if bad == 'wrong_owner': settings.demo_subject_id = reader.subject_id
    if bad == 'missing_actor': settings.demo_relative_actor_id = 'missing'
    if bad == 'extra_space':
        session.add(Subject(subject_id='private-space', display_name='private', owner_actor_id=owner.actor_id)); session.commit()
    assert client.post('/api/v1/accounts/demo-session', json={'role': 'owner'}).status_code == 404


def test_demo_sessions_keep_real_permissions_and_other_devices(app, client, session):
    owner, reader, oh, rh, public, _ = configured(app, client, session)
    # A second real ingestion with its own idempotency key, then normal worker/review.
    from app.worker import ProcessingWorker
    uploaded = client.post('/api/v1/episodes', headers=oh, data={
        'subject_id': owner.subject_id, 'recording_consent_id': owner.consent_id,
        'idempotency_key': 'private-demo', 'source': 'IOS_MIC',
        'recorded_at': '2026-10-17T01:00:00Z', 'audio_ref': 'private.m4a'},
        files={'file': ('private.m4a', b'PRIVATE-AUDIO', 'audio/mp4')})
    assert uploaded.status_code == 201, uploaded.text
    private = uploaded.json()['episode_id']
    worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert client.patch(f'/api/v1/episodes/{private}/transcript-review', headers=oh, json={'transcript': '不开放的往事'}).status_code == 200
    worker.run_once(); worker.run_once()
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant = client.post(root+'/grants', headers=oh, json={'episode_id': public,
        'reader_actor_id': reader.actor_id, 'include_audio_confirmed': True, 'cloud_processing_allowed': True})
    assert grant.status_code == 201, grant.text
    o, a = enter(client, 'owner')
    _, another = enter(client, 'owner')
    r, b = enter(client, 'relative')
    assert o['actor_id'] == owner.actor_id and r['actor_id'] == reader.actor_id
    assert o['actor_token'] != r['actor_token']
    for headers, role in [(a, 'owner'), (b, 'relative')]:
        spaces = client.get('/api/v1/workbench/spaces', headers=headers).json()
        assert spaces['demo_role'] == role and spaces['demo_subject_id'] == owner.subject_id
    assert {x['episode_id'] for x in client.get(root+'/stories', headers=a).json()['items']} == {public, private}
    assert [x['episode_id'] for x in client.get(root+'/stories', headers=b).json()['items']] == [public]
    assert client.get(root+f'/stories/{private}/audio', headers=b).status_code == 404
    assert client.get(root+f'/stories/{public}/audio', headers=b).status_code == 200
    assert client.put(root+'/vocabulary', headers=b, json={'text': 'forbidden'}).status_code == 404
    assert client.post('/api/v1/consents', headers=b, json={'subject_id': owner.subject_id, 'scope': 'RECORDING'}).status_code in (403, 404)
    assert client.post('/api/v1/accounts/logout', headers=a).status_code == 200
    assert client.get('/api/v1/session', headers=a).status_code == 401
    assert client.get('/api/v1/session', headers=another).status_code == 200
    assert client.get('/api/v1/session', headers=b).status_code == 200
    session.expire_all()
    devices = list(session.scalars(select(DeviceCredential)))
    assert all(0 < (as_utc(d.expires_at)-utcnow()).total_seconds() <= 86400 for d in devices)
    assert client.delete(root+'/grants/'+grant.json()['grant_id'], headers=oh).status_code == 200
    assert client.get(root+f'/stories/{public}/audio', headers=b).status_code == 404


def test_transport_origin_and_rate_limit_still_apply(app, client, session):
    configured(app, client, session)
    url='/api/v1/accounts/demo-session'
    assert client.post('http://remote.invalid'+url, json={'role': 'owner'}).status_code == 422
    assert client.post(url, json={'role': 'owner'}, headers={'Origin': 'https://other.invalid'}).status_code == 422
    for _ in range(10): enter(client, 'owner')
    assert client.post(url, json={'role': 'owner'}).status_code == 429
