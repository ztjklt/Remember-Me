"""Material validity is durable; permission validity is checked per operation.

These use real API/storage transactions with a bounded model double, not live
model quality acceptance. No fixture is silently rebased after an auth change.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select

from app.access import source_basis
from app.models import Episode, MemoryItem, ProfileCandidate, ProfileRefresh
from app.profiles import approved_traits, run_profile_once
from test_agent_workbench import setup_pair


class Proposal:
    calls = 0

    def propose(self, materials):
        self.calls += 1
        return {'candidates': [{'domain': 'PREFERENCES', 'kind': 'habit',
            'statement': '在本次材料中提到散步', 'context': '只描述这一次讲述',
            'evidence_ids': [materials[0]['evidence_id']], 'counter_evidence_ids': []}],
            'model_version': 'deterministic-test', 'prompt_version': 'test'}


def created(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    queued = client.post(root+'/profile-candidates/refresh', headers=oh,
                         json={'cloud_consent_id': cloud})
    assert queued.status_code == 202, queued.text
    run_profile_once(app.state.database, Proposal())
    item = client.get(root+'/profile-candidates', headers=oh).json()['items'][0]
    assert item['status'] == 'pending'
    return owner, reader, oh, rh, ep, cloud, root, item


@pytest.mark.parametrize('change', ['new_cloud_consent', 'story_grant', 'grant_revocation'])
def test_confirmed_understanding_survives_permission_only_changes(app, client, session, change):
    owner, reader, oh, rh, ep, cloud, root, item = created(app, client, session)
    path = root+'/profile-candidates/'+item['candidate_id']
    assert client.post(path+'/confirm', headers=oh).status_code == 200
    session.expire_all()
    before = source_basis(session, owner.subject_id)
    session.rollback()
    if change == 'new_cloud_consent':
        response = client.post('/api/v1/consents', headers=oh,
                              json={'subject_id': owner.subject_id, 'scope': 'CLOUD_TWIN'})
        assert response.status_code == 201
        cloud = response.json()['consent_id']
    else:
        response = client.post(root+'/grants', headers=oh, json={'episode_id': ep,
            'reader_actor_id': reader.actor_id, 'include_audio_confirmed': True,
            'cloud_processing_allowed': True})
        assert response.status_code == 201
        if change == 'grant_revocation':
            assert client.delete(root+'/grants/'+response.json()['grant_id'], headers=oh).status_code == 200
            assert client.get(root+f'/stories/{ep}/audio', headers=rh).status_code == 404
    session.expire_all()
    assert before != source_basis(session, owner.subject_id), 'publication guard must still observe authorization'
    session.rollback()
    viewed = client.get(root+'/profile-candidates', headers=oh).json()['items'][0]
    assert viewed['status'] == 'confirmed', viewed
    assert viewed['source_version'] == item['source_version']
    narrative = client.get(root+'/narrative', headers=oh).json()
    assert any(v['candidate_id'] == item['candidate_id'] and v['status'] == 'confirmed'
               for v in narrative['understandings'])
    seen = []
    class Inspect:
        def answer(self, question, candidates):
            seen.extend(candidates)
            return dict(answer='目前不知道。', response_type='UNKNOWN', evidence_ids=[], confidence=0, model_version='test')
    app.state.twin_client = Inspect()
    answer = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
                         json={'question': '这次讲述有什么偏好？', 'cloud_consent_id': cloud})
    assert answer.status_code == 200, answer.text
    assert any(item['statement'] in t for c in seen for t in c['traits'])


def test_pending_candidate_can_be_confirmed_after_new_consent_but_not_after_source_edit(app, client, session):
    owner, _, oh, _, ep, _, root, item = created(app, client, session)
    client.post('/api/v1/consents', headers=oh, json={'subject_id': owner.subject_id, 'scope': 'CLOUD_TWIN'})
    path = root+'/profile-candidates/'+item['candidate_id']+'/confirm'
    assert client.post(path, headers=oh).status_code == 200
    with app.state.database.session() as writer:
        writer.get(Episode, ep).transcript += '。这段内容后来有了变化。'
        writer.commit()
    assert client.get(root+'/profile-candidates', headers=oh).json()['items'][0]['status'] == 'stale'
    assert client.post(path, headers=oh).status_code == 409
    session.expire_all()
    assert not approved_traits(session, owner.subject_id)


def test_revoked_cloud_consent_stops_calls_without_erasing_local_understanding(app, client, session):
    owner, _, oh, _, ep, cloud, root, item = created(app, client, session)
    assert client.post(root+'/profile-candidates/'+item['candidate_id']+'/confirm', headers=oh).status_code == 200
    assert client.post('/api/v1/consents/'+cloud+'/revoke', headers=oh).status_code == 200
    assert client.get(root+'/profile-candidates', headers=oh).json()['items'][0]['status'] == 'confirmed'
    app.state.twin_client = object()  # No callable model: rejection must precede dispatch.
    assert client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question': '喜欢什么？', 'cloud_consent_id': cloud}).status_code == 403
    assert client.post(root+'/profile-candidates/refresh', headers=oh,
        json={'cloud_consent_id': cloud}).status_code == 403


@pytest.mark.parametrize('old_status', ['pending', 'confirmed'])
def test_legacy_hash_stays_stale_without_rebasing(app, client, session, old_status):
    owner, _, oh, _, _, _, root, item = created(app, client, session)
    row = session.get(ProfileCandidate, item['candidate_id'])
    legacy_basis = source_basis(session, owner.subject_id, include_profiles=False)
    row.source_basis, row.status = legacy_basis, old_status
    session.commit()
    viewed = client.get(root+'/profile-candidates', headers=oh).json()['items'][0]
    assert viewed['status'] == 'stale' and viewed['stored_status'] == old_status
    assert client.post(root+'/profile-candidates/'+row.candidate_id+'/confirm', headers=oh).status_code == 409
    session.expire_all()
    assert not approved_traits(session, owner.subject_id)
    assert (row.source_basis, row.status) == (legacy_basis, old_status)


@pytest.mark.parametrize('change', ['new_consent', 'revoke_consent', 'grant_revocation', 'profile', 'source', 'delete'])
def test_inflight_profile_rechecks_permissions_and_sources_without_retry(app, client, session, change):
    owner, reader, oh, _, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates'
    if change == 'grant_revocation':
        grant = client.post(root.removesuffix('/profile-candidates')+'/grants', headers=oh,
            json={'episode_id': ep, 'reader_actor_id': reader.actor_id,
                  'include_audio_confirmed': True, 'cloud_processing_allowed': True})
        assert grant.status_code == 201
    if change == 'profile':
        client.post(root+'/refresh', headers=oh, json={'cloud_consent_id': cloud})
        run_profile_once(app.state.database, Proposal())
        existing = client.get(root, headers=oh).json()['items'][0]
    job = client.post(root+'/refresh', headers=oh, json={'cloud_consent_id': cloud}).json()['job_id']
    entered, release = Event(), Event()
    class Slow(Proposal):
        def propose(self, materials):
            entered.set()
            assert release.wait(15)
            return super().propose(materials)
    provider = Slow()
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    memory_id = memory.memory_item_id
    session.rollback()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(run_profile_once, app.state.database, provider)
        assert entered.wait(15)
        try:
            if change == 'new_consent':
                assert client.post('/api/v1/consents', headers=oh,
                    json={'subject_id': owner.subject_id, 'scope': 'CLOUD_TWIN'}).status_code == 201
            elif change == 'revoke_consent':
                assert client.post('/api/v1/consents/'+cloud+'/revoke', headers=oh).status_code == 200
            elif change == 'grant_revocation':
                assert client.delete(root.removesuffix('/profile-candidates')+'/grants/'+
                    grant.json()['grant_id'], headers=oh).status_code == 200
            elif change == 'profile':
                assert client.post(root+'/'+existing['candidate_id']+'/confirm', headers=oh).status_code == 200
            elif change == 'source':
                with app.state.database.session() as writer:
                    writer.get(Episode, ep).transcript += '。新的说法。'
                    writer.commit()
            else:
                assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory_id}', headers=oh).status_code == 200
        finally:
            release.set()
        future.result(timeout=20)
    session.expire_all()
    assert session.get(ProfileRefresh, job).status == 'failed'
    assert len(list(session.scalars(select(ProfileCandidate)))) == (1 if change == 'profile' else 0)
    assert provider.calls == 1
