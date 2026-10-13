"""Manual language support: provenance and sharing, not ASR accuracy tests."""
from sqlalchemy import select
from app.models import Episode, MemoryItem, Evidence
from app.worker import ProcessingWorker
from app.language_support import store_supplement
from app.materials import effective_materials
from test_agent_workbench import setup_pair


def reviewed_note(app, client, session, pending=False):
    owner, reader, oh, rh, old, cloud = setup_pair(app, client, session)
    result = client.post('/api/v1/episodes', headers=oh, data={
        'subject_id':owner.subject_id,'recording_consent_id':owner.consent_id,
        'idempotency_key':'manual-words', 'source':'ANDROID_MIC',
        'recorded_at':'2026-10-08T12:00:00Z','audio_ref':'note.m4a'},
        files={'file':('note.m4a',b'FIXTURE-AUDIO','audio/mp4')})
    assert result.status_code == 201, result.text
    ep = result.json()['episode_id']
    if pending:
        target=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==old))
        result=client.post(f'/api/v1/workbench/subjects/{owner.subject_id}/revisions',headers=oh,
            json={'episode_id':ep,'target_memory_id':target.memory_item_id,'kind':'correction'})
        assert result.status_code==201,result.text
    worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert worker.run_once() is None  # no extraction before review
    body = {'transcript':'我喜欢散步。','supplement':'这里的老隗是我的同事隗师傅，不是亲戚。'}
    path=f'/api/v1/episodes/{ep}/transcript-review'
    assert client.patch(path,headers=rh,json=body).status_code==404
    assert client.patch(path,headers=oh,json=body).status_code==200
    assert client.patch(path,headers=oh,json=body).status_code==200
    assert client.patch(path,headers=oh,json={**body,'supplement':'偷偷修改'}).status_code==422
    worker.run_once();worker.run_once();session.expire_all()
    return owner,reader,oh,rh,ep,cloud


def test_vocabulary_is_private_not_automatic_material(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    saved=client.put(root+'/vocabulary',headers=oh,json={'text':'私密词表 隗师傅'})
    assert saved.status_code==200 and saved.json()['automatic_model_use'] is False
    assert client.get(root+'/vocabulary',headers=oh).json()['text']=='私密词表 隗师傅'
    client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True})
    assert client.get(root+'/vocabulary',headers=rh).status_code==404
    assert client.put(root+'/vocabulary',headers=rh,json={'text':'改掉'}).status_code==404
    assert '私密词表' not in client.get(root+'/stories',headers=rh).text
    assert client.put(root+'/vocabulary',headers=oh,json={'text':'字'*3001}).status_code==422


def test_note_keeps_provenance_and_explicit_story_grant(app,client,session):
    owner,reader,oh,rh,ep,cloud=reviewed_note(app,client,session)
    row=session.get(Episode,ep)
    assert row.stt_transcript and row.transcript=='我喜欢散步。'
    note=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep,MemoryItem.model_version=='owner-input'))
    assert note is not None and note.source_type=='CALIBRATION'
    evidence=session.get(Evidence,note.evidence_ids[0])
    assert evidence.span_start is None and evidence.source_ref.startswith('owner-supplement:')
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    assert client.get(root+'/stories',headers=rh).status_code==404
    grant=client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,'cloud_processing_allowed':True})
    assert grant.status_code==201,grant.text
    result=client.get(root+'/stories',headers=rh).json()['items'][0]
    assert not result['unavailable']
    assert any(m['origin']=='owner_supplement' for m in result['memories'])
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==200
    assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{note.memory_item_id}',headers=oh).status_code==200
    session.expire_all();store_supplement(session,session.get(Episode,ep));session.commit()
    assert session.get(MemoryItem,note.memory_item_id).deleted_at is not None
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==404


def test_shared_note_correction_stays_private(app,client,session):
    owner,reader,oh,rh,ep,cloud=reviewed_note(app,client,session)
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    assert client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True}).status_code==201
    note=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep,MemoryItem.model_version=='owner-input'))
    assert client.patch(f'/api/v1/subjects/{owner.subject_id}/memories/{note.memory_item_id}',headers=oh,json={'content':'仅本人可看的新修订'}).status_code==200
    stories=client.get(root+'/stories',headers=rh)
    assert stories.json()['items'][0]['unavailable'] is True
    assert '仅本人可看的新修订' not in stories.text
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==404


def test_pending_revision_note_is_not_active(app,client,session):
    owner,reader,oh,rh,ep,cloud=reviewed_note(app,client,session,pending=True)
    note=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep,MemoryItem.model_version=='owner-input'))
    assert note.review_state=='pending'
    materials=effective_materials(session,owner.subject_id,{ep})
    assert materials==[]


def test_shared_note_is_searchable(app,client,session):
    owner,reader,oh,rh,ep,cloud=reviewed_note(app,client,session)
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    assert client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True}).status_code==201
    result=client.get(f'/api/v1/subjects/{owner.subject_id}/memory-search',headers=rh,params={'q':'同事隗师傅'})
    assert result.status_code==200,result.text
    assert any('隗师傅' in item['statement'] for item in result.json()['items'])
