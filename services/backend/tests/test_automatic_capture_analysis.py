"""Automatic capture contract: draft first, explicit Save, durable cumulative job."""
from sqlalchemy import select
from app.models import Episode, ProfileRefresh, ProfileCandidate
from app.worker import ProcessingWorker
from app.profiles import run_profile_once
from app.automatic_profiles import enqueue_automatic_profile, automatic_retry
from test_agent_workbench import setup_pair


def record_draft(app, client, owner, auth, key):
    result = client.post('/api/v1/episodes', headers=auth, data={
        'subject_id': owner.subject_id, 'recording_consent_id': owner.consent_id,
        'idempotency_key': key, 'source': 'WORK_3200',
        'recorded_at': '2026-10-16T12:00:00Z', 'audio_ref': 'test.webm'},
        files={'file': ('test.webm', b'EXPLICIT-TEST-AUDIO-' + key.encode(), 'audio/webm')})
    assert result.status_code == 201, result.text
    id = result.json()['episode_id']
    worker = ProcessingWorker(app.state.database, app.state.object_store,
        app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert client.get(f'/api/v1/episodes/{id}/transcript-review', headers=auth).json()['state'] == 'reviewing'
    return id, worker


def save(client, auth, id, cloud):
    result = client.patch(f'/api/v1/episodes/{id}/transcript-review', headers=auth,
        json={'transcript': '我每天都会到公园散步。', 'supplement': '今天和老朋友一起。',
              'cloud_analysis_consent_id': cloud})
    assert result.status_code == 200, result.text


def test_save_then_memory_then_cumulative_analysis_and_replay(app, client, session):
    owner, _, oh, _, old, cloud = setup_pair(app, client, session)
    id, worker = record_draft(app, client, owner, oh, 'automatic-one')
    assert not list(session.scalars(select(ProfileRefresh)))
    session.rollback()
    save(client, oh, id, cloud)
    worker.run_once()  # extract is not the final publication
    assert not list(session.scalars(select(ProfileRefresh)))
    session.rollback()
    worker.run_once()  # MODEL commits memories and durable cumulative task
    row = session.scalar(select(ProfileRefresh))
    assert row.status == 'queued' and row.request_payload['episode_ids'] == [id]
    assert session.get(Episode, id).status == 'ready'
    job_id = row.job_id
    session.rollback()
    save(client, oh, id, cloud)  # lost PATCH response replay
    assert worker.run_once() is None
    seen = []
    class Model:
        def propose(self, materials):
            seen.extend(materials)
            return {'candidates': [], 'model_version': 'test', 'prompt_version': 'test'}
    assert run_profile_once(app.state.database, Model()) == job_id
    assert {old, id}.issubset({m['episode_id'] for m in seen})
    session.expire_all()
    assert session.get(ProfileRefresh, job_id).status == 'complete'
    assert len(list(session.scalars(select(ProfileRefresh)))) == 1
    stories = client.get(f'/api/v1/workbench/subjects/{owner.subject_id}/stories', headers=oh).json()['items']
    assert next(s for s in stories if s['episode_id']==id)['cumulative_analysis']['status']=='complete'


def test_queued_coalesces_but_running_gets_successor(app, client, session):
    owner, _, oh, _, _, cloud = setup_pair(app, client, session)
    ids = []
    for key in ['auto-a','auto-b','auto-c']:
        id, worker = record_draft(app, client, owner, oh, key)
        save(client, oh, id, cloud); worker.run_once(); worker.run_once(); ids.append(id)
        session.expire_all()
        rows = list(session.scalars(select(ProfileRefresh)))
        if key=='auto-b':
            assert len(rows)==1 and rows[0].request_payload['episode_ids']==ids
            rows[0].status='running'; session.commit()
        else: session.rollback()
    rows = list(session.scalars(select(ProfileRefresh)))
    assert sorted(r.status for r in rows)==['queued','running']
    assert next(r for r in rows if r.status=='queued').request_payload['episode_ids']==[ids[-1]]


def test_revoked_consent_retains_memories_without_sending_analysis(app, client, session):
    owner, _, oh, _, _, cloud = setup_pair(app, client, session)
    id, worker = record_draft(app, client, owner, oh, 'auto-revoke')
    save(client, oh, id, cloud)
    assert client.post(f'/api/v1/consents/{cloud}/revoke', headers=oh).status_code == 200
    worker.run_once(); worker.run_once()
    session.expire_all()
    ep = session.get(Episode,id)
    assert ep.status=='ready'
    assert ep.capture_metadata['automatic_profile']['status']=='authorization_required'
    assert not list(session.scalars(select(ProfileRefresh)))


def test_other_actor_consent_cannot_enable_automatic_analysis(app, client, session):
    owner, reader, oh, rh, _, _ = setup_pair(app, client, session)
    id, _ = record_draft(app, client, owner, oh, 'auto-wrong-identity')
    other = client.post('/api/v1/consents',headers=rh,json={'subject_id':reader.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    result=client.patch(f'/api/v1/episodes/{id}/transcript-review',headers=oh,
        json={'transcript':'测试', 'cloud_analysis_consent_id':other})
    assert result.status_code in (403,404)
    assert client.get(f'/api/v1/episodes/{id}/transcript-review',headers=oh).json()['state']=='reviewing'


def test_automatic_retry_is_bounded_and_schema_errors_are_not_retried():
    row=ProfileRefresh(request_payload={'automatic':True},status='failed')
    assert automatic_retry(row,RuntimeError('temporary'))
    assert automatic_retry(row,ValueError('SOURCE_CHANGED'))
    assert not automatic_retry(row,RuntimeError('temporary'))
    assert not automatic_retry(ProfileRefresh(request_payload={'automatic':True}),ValueError('invalid schema'))
    assert not automatic_retry(ProfileRefresh(request_payload={}),RuntimeError('temporary'))
