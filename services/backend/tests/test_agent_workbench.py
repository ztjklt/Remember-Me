"""Deterministic contract tests; these do NOT count as real-model acceptance."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import select, delete

from app.models import MemoryItem
import pytest
from app.seed import seed_development_data
from test_twin_voice import _record, TinyEncoder, QuoteTwin


def setup_pair(app, client, session):
    owner = seed_development_data(session, subject_name="记录者", actor_name="记录者")
    reader = seed_development_data(session, subject_name="读者自己", actor_name="读者")
    oh = {"Authorization": "Bearer " + owner.actor_token}
    rh = {"Authorization": "Bearer " + reader.actor_token}
    episode = _record(client, app, owner.subject_id, owner.consent_id, oh)
    app.state.embedding_encoder = TinyEncoder()
    app.state.twin_client = QuoteTwin()
    app.state.settings.ai_backend = "http"
    cloud = client.post('/api/v1/consents', headers=oh,
                        json={"subject_id": owner.subject_id, "scope": "CLOUD_TWIN"}).json()['consent_id']
    return owner, reader, oh, rh, episode, cloud


def test_reader_cannot_self_authorize(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    for scope in ('RECORDING', 'VOICE', 'CLOUD_TWIN'):
        response = client.post('/api/v1/consents', headers=rh,
                               json={"subject_id": owner.subject_id, "scope": scope})
        assert response.status_code in (403, 404)


def test_story_grant_and_revocation(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    assert client.get(root + '/stories', headers=rh).status_code == 404
    granted = client.post(root + '/grants', headers=oh, json={
        'episode_id': ep, 'reader_actor_id': reader.actor_id, 'include_audio_confirmed': True,
        'cloud_processing_allowed': True})
    assert granted.status_code == 201, granted.text
    stories = client.get(root + '/stories', headers=rh)
    assert stories.status_code == 200
    assert [x['episode_id'] for x in stories.json()['items']] == [ep]
    assert client.get(root + f'/stories/{ep}/audio', headers=rh).status_code == 200
    answered = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=rh,
        json={'question': '喜欢什么？', 'cloud_consent_id': granted.json()['grant_id']})
    assert answered.status_code == 200, answered.text
    assert client.delete(root + '/grants/' + granted.json()['grant_id'], headers=oh).status_code == 200
    assert client.get(root + f'/stories/{ep}/audio', headers=rh).status_code == 404
    assert client.get(f'/api/v1/subjects/{owner.subject_id}/twin/answers/' + answered.json()['answer_id'], headers=rh).status_code == 404


@pytest.mark.parametrize('round_number',range(3))
def test_inflight_correction_rejects_answer(app, client, session,round_number):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    entered, release = Event(), Event()
    class Delayed(QuoteTwin):
        def answer(self, question, candidates):
            entered.set()
            assert release.wait(15)
            return super().answer(question, candidates)
    app.state.twin_client = Delayed()
    def ask():
        with TestClient(app) as other_client:
            return other_client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
                                    json={'question': '喜欢什么？', 'cloud_consent_id': cloud})
    with ThreadPoolExecutor() as pool:
        future = pool.submit(ask)
        assert entered.wait(15)
        try:
            result = client.patch(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}',
                                  headers=oh, json={'content': '我喜欢游泳'})
            assert result.status_code == 200
        finally:
            release.set()
        response = future.result()
    assert response.status_code == 409, response.text
    assert response.json()['error_code'] == 'SOURCE_CHANGED'


def test_import_waits_for_review_and_revision_confirmation(app, client, session):
    from app.worker import ProcessingWorker
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    old = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    uploaded = client.post('/api/v1/episodes', headers=oh, data={
        'subject_id': owner.subject_id, 'recording_consent_id': owner.consent_id,
        'idempotency_key': 'new-correction', 'source': 'IMPORT',
        'recorded_at': '2026-10-07T12:00:00Z', 'audio_ref': 'correction.webm'},
        files={'file': ('correction.webm', b'EXPLICIT-TEST-AUDIO', 'audio/webm')})
    assert uploaded.status_code == 201, uploaded.text
    new_ep = uploaded.json()['episode_id']
    proposed = client.post(root + '/revisions', headers=oh, json={
        'target_memory_id': old.memory_item_id, 'episode_id': new_ep, 'kind': 'correction'})
    assert proposed.status_code == 201, proposed.text
    worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider,
                              app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert worker.run_once() is None
    review = client.get(f'/api/v1/episodes/{new_ep}/transcript-review', headers=oh)
    assert review.json()['state'] == 'reviewing'
    assert client.patch(f'/api/v1/episodes/{new_ep}/transcript-review', headers=oh,
                        json={'transcript': '我更正一下，我喜欢游泳。'}).status_code == 200
    worker.run_once()
    worker.run_once()
    session.expire_all()
    new_memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == new_ep))
    assert new_memory.review_state == 'pending'
    confirmed = client.post(root + '/revisions/' + proposed.json()['revision_id'] + '/confirm', headers=oh)
    assert confirmed.status_code == 200, confirmed.text
    session.expire_all()
    assert session.get(MemoryItem, old.memory_item_id).review_state == 'superseded'
    assert session.get(MemoryItem, new_memory.memory_item_id).review_state == 'active'
    # Repeated confirmation is idempotent.
    again = client.post(root + '/revisions/' + proposed.json()['revision_id'] + '/confirm', headers=oh)
    assert again.status_code == 200
    assert again.json() == confirmed.json()


def test_question_request_does_not_share_answer(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    client.post(root + '/grants', headers=oh, json={'episode_id': ep,
        'reader_actor_id': reader.actor_id, 'include_audio_confirmed': True})
    pending = client.post(root + '/requests', headers=rh, json={'text': '后来发生了什么？'})
    assert pending.status_code == 201, pending.text
    path = root + '/requests/' + pending.json()['request_id']
    assert client.patch(path, headers=rh, json={'status': 'declined'}).status_code == 404
    assert client.patch(path, headers=oh, json={'status': 'snoozed'}).status_code == 200
    assert client.patch(path, headers=oh, json={'status': 'answered', 'answer_episode_id': ep}).status_code == 200


def test_legacy_captor_loses_access_after_explicit_owner_mapping(app, client, session):
    from app.models import Subject
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    session.get(Subject, owner.subject_id).owner_actor_id = reader.actor_id
    session.commit()
    for suffix in ('', '/audio', '/result', '/transcript-review'):
        assert client.get('/api/v1/episodes/' + ep + suffix, headers=oh).status_code == 404
    assert client.post('/api/v1/episodes/' + ep + '/retry', headers=oh).status_code == 404


def test_revision_rejects_unreviewed_legacy_ready_episode(app, client, session):
    from app.models import Episode
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    target = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    # The target cannot be the new recording, but a legacy ready episode is not
    # eligible even when transcript_reviewed_at was never written by old clients.
    legacy = _record(client, app, reader.subject_id, reader.consent_id, rh)
    row = session.get(Episode, legacy)
    row.subject_id = owner.subject_id
    row.transcript_reviewed_at = None
    row.source = 'ANDROID_MIC'
    session.commit()
    response = client.post(f'/api/v1/workbench/subjects/{owner.subject_id}/revisions', headers=oh,
        json={'target_memory_id': target.memory_item_id, 'episode_id': legacy, 'kind': 'correction'})
    assert response.status_code == 422


@pytest.mark.parametrize('iteration', range(3))
@pytest.mark.parametrize('mutation', ['delete', 'revoke'])
def test_independent_request_race(app, client, session, mutation, iteration):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant = client.post(root+'/grants', headers=oh, json={'episode_id':ep,
        'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,'cloud_processing_allowed':True}).json()
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    entered, release = Event(), Event()
    class Delayed(QuoteTwin):
        def answer(self, question, candidates):
            entered.set()
            assert release.wait(15)
            return super().answer(question,candidates)
    app.state.twin_client=Delayed()
    def ask():
        with TestClient(app) as independent:
            return independent.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=rh,
                json={'question':'喜欢什么？','cloud_consent_id':grant['grant_id']})
    with ThreadPoolExecutor() as pool:
        future=pool.submit(ask)
        assert entered.wait(15)
        try:
            path=(root+'/grants/'+grant['grant_id'] if mutation=='revoke' else
                  f'/api/v1/subjects/{owner.subject_id}/memories/'+memory.memory_item_id)
            assert client.delete(path,headers=oh).status_code==200
        finally:
            release.set()
        result=future.result()
    assert result.status_code==409, result.text


def test_private_aggregate_never_enters_reader_inputs(app, client, session):
    from app.models import PersonTrait
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    trait=session.scalar(select(PersonTrait).where(PersonTrait.subject_id==owner.subject_id))
    trait.statement='PRIVATE-MEDICAL-SECRET'
    session.commit()
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant=client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,
        'include_audio_confirmed':True,'cloud_processing_allowed':True}).json()
    class Inspect(QuoteTwin):
        def answer(self,q,candidates):
            assert 'PRIVATE-MEDICAL-SECRET' not in str(candidates)
            return super().answer(q,candidates)
    app.state.twin_client=Inspect()
    result=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=rh,
        json={'question':'喜欢什么？','cloud_consent_id':grant['grant_id']})
    assert result.status_code==200, result.text
    assert 'PRIVATE-MEDICAL-SECRET' not in client.get(root+'/portrait',headers=rh).text
    assert client.get(f'/api/v1/subjects/{owner.subject_id}/person-model',headers=rh).status_code==404


def test_confirmed_time_change_is_not_unresolved_conflict(app, client, session):
    from app.models import Episode, MemoryRevision, PersonTrait, GraphFact
    from app.repositories.person_model import PersonModelRepository
    owner, reader, oh, rh, ep, cloud=setup_pair(app,client,session)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    new_ep=_record(client,app,reader.subject_id,reader.consent_id,rh)
    session.get(Episode,new_ep).subject_id=owner.subject_id
    session.execute(delete(PersonTrait).where(PersonTrait.subject_id==reader.subject_id))
    session.execute(delete(GraphFact).where(GraphFact.subject_id==reader.subject_id))
    new=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==new_ep))
    old.content='我喜欢散步';new.content='我不喜欢散步'
    old.memory_type=new.memory_type='PREFERENCE'
    old.item_metadata=new.item_metadata={'domain':'PREFERENCES'}
    new.review_state='pending'
    session.add(MemoryRevision(revision_id='time-change',subject_id=owner.subject_id,
        target_memory_id=old.memory_item_id,episode_id=new_ep,kind='change',time_text='最近'))
    session.commit()
    response=client.post(f'/api/v1/workbench/subjects/{owner.subject_id}/revisions/time-change/confirm',headers=oh)
    assert response.status_code==200,response.text
    session.expire_all()
    traits=list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id==owner.subject_id)))
    assert len(traits)==2
    assert all(t.status!='unresolved' for t in traits)


def test_search_revoked_during_encoding_returns_no_content(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant=client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,
        'include_audio_confirmed':True}).json()
    entered,release=Event(),Event()
    class Delayed(TinyEncoder):
        def encode(self,texts):
            entered.set()
            assert release.wait(15)
            return super().encode(texts)
    app.state.embedding_encoder=Delayed()
    def search():
        with TestClient(app) as independent:
            return independent.get(f'/api/v1/subjects/{owner.subject_id}/memory-search?q=喜欢',headers=rh)
    with ThreadPoolExecutor() as pool:
        future=pool.submit(search)
        assert entered.wait(15)
        try:
            assert client.delete(root+'/grants/'+grant['grant_id'],headers=oh).status_code==200
        finally:
            release.set()
        response=future.result()
    assert response.status_code==409,response.text
