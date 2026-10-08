"""Deterministic update state machine tests; no real model acceptance claims."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.models import ProfileCandidate, Episode, MemoryItem
from app.access import source_basis
from app.materials import effective_materials
from app.profiles import approved_traits
from test_agent_workbench import setup_pair


def prepare(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    source = effective_materials(session, owner.subject_id, {ep})[0]['evidence'][0]
    session.commit()
    basis = source_basis(session, owner.subject_id, include_profiles=False)
    for id in ['target','next','other']:
        session.add(ProfileCandidate(candidate_id=id,subject_id=owner.subject_id,domain='PREFERENCES',kind='habit',
            statement='原来的理解' if id=='target' else '新理解'+id, context='测试情境',evidence_ids=[source['evidence_id']],
            counter_evidence_ids=[],independent_episodes=1,source_basis=basis,status='pending',model_version='test',prompt_version='test'))
    session.commit()
    root=f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates'
    assert client.post(root+'/target/confirm',headers=oh).status_code==200
    return owner,oh,rh,ep,cloud,root


def proposal(client,root,headers,action='SUPPORT',candidate='next'):
    return client.post(root+'/updates',headers=headers,json={'candidate_id':candidate,'action':action,
        'target_candidate_id':None if action=='ADD' else 'target','reason':'本人核对两条的情境和含义',
        'time_text':'后来' if action=='CHANGE' else ''})


@pytest.mark.parametrize('action',['ADD','SUPPORT','CONFLICT','CHANGE'])
def test_owner_actions_are_atomic_audited_and_idempotent(app,client,session,action):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    assert proposal(client,root,rh,action).status_code==404
    assert client.get(root+'/updates',headers=rh).status_code==404
    r=proposal(client,root,oh,action); assert r.status_code==201,r.text
    update=r.json();path=root+'/updates/'+update['update_id']+'/confirm'
    assert client.post(path,headers=rh).status_code==404
    r=client.post(path,headers=oh);assert r.status_code==200,r.text
    assert client.post(path,headers=oh).json()==r.json()
    history=client.get(root+'/updates',headers=oh).json()['items']
    assert len(history)==1 and history[0]['status']=='confirmed'
    session.expire_all()
    current=approved_traits(session,owner.subject_id)
    if action=='CONFLICT':
        assert not current
        assert history[0]['question']
    elif action=='SUPPORT':
        assert len(current)==1 and current[0].statement=='原来的理解'
        assert current[0].candidate_id not in {'target','next'}
    elif action=='CHANGE':
        assert len(current)==1 and current[0].statement=='新理解next'
        assert '后来' in current[0].context
    else:
        assert len(current)==2
    if action!='ADD':
        assert client.post(root+'/target/confirm',headers=oh).status_code==409


@pytest.mark.parametrize('mutation',['source','target','delete'])
def test_changed_source_or_target_rejects_pending_update(app,client,session,mutation):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    r=proposal(client,root,oh);assert r.status_code==201,r.text
    if mutation=='source':
        session.get(Episode,ep).transcript+='。补充说明';session.commit()
    elif mutation=='target':
        client.post(root+'/target/reject',headers=oh)
    else:
        memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
        client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}',headers=oh)
    assert client.post(root+'/updates/'+r.json()['update_id']+'/confirm',headers=oh).status_code==409


def test_rejection_and_competing_updates_do_not_reapply(app,client,session):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    first=proposal(client,root,oh).json()
    second=proposal(client,root,oh,'CHANGE','other').json()
    assert client.post(root+'/updates/'+first['update_id']+'/confirm',headers=oh).status_code==200
    assert client.post(root+'/updates/'+second['update_id']+'/confirm',headers=oh).status_code==409
    assert client.post(root+'/updates/'+second['update_id']+'/reject',headers=oh).status_code==200
    assert client.post(root+'/updates/'+second['update_id']+'/confirm',headers=oh).status_code==409


def test_additional_recording_requires_explicit_target_revalidation(app,client,session):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    # New material makes an old confirmed understanding stale. Confirmation of a
    # SUPPORT update may revalidate the target only if its saved sources survive.
    session.get(Episode,ep).transcript+='。新的无关材料';session.commit()
    effective_materials(session,owner.subject_id,{ep});session.commit()
    row=session.get(ProfileCandidate,'next');row.source_basis=source_basis(session,owner.subject_id,include_profiles=False);session.commit()
    assert not approved_traits(session,owner.subject_id)
    r=proposal(client,root,oh);assert r.status_code==201,r.text
    confirmed=client.post(root+'/updates/'+r.json()['update_id']+'/confirm',headers=oh)
    assert confirmed.status_code==200,confirmed.text
    assert len(approved_traits(session,owner.subject_id))==1


def test_inflight_twin_cannot_publish_after_profile_change(app,client,session):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    r=proposal(client,root,oh);assert r.status_code==201,r.text
    entered,release=Event(),Event()
    class Slow:
        def answer(self,question,candidates):
            entered.set();assert release.wait(15)
            return dict(answer='现有记录还不足以确定。',response_type='UNKNOWN',evidence_ids=[],confidence=0,model_version='test')
    app.state.twin_client=Slow()
    def ask():
        with TestClient(app) as other:
            return other.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
                json={'question':'偏好是什么？','cloud_consent_id':cloud})
    with ThreadPoolExecutor() as pool:
        future=pool.submit(ask);assert entered.wait(15)
        try: assert client.post(root+'/updates/'+r.json()['update_id']+'/confirm',headers=oh).status_code==200
        finally: release.set()
        assert future.result().status_code==409
