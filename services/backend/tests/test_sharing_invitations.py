"""Real API/database tests: claiming must never grant access."""
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models import Account, Episode, StoryGrant, utcnow
from test_agent_workbench import setup_pair


def prepare(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    for name, person in [('owner_one', owner), ('reader_one', reader)]:
        session.add(Account(username=name, actor_id=person.actor_id, salt='00'*16, password_hash='fixture'))
    session.commit()
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    return owner, reader, oh, rh, ep, root


def invite(client, oh, root, ep, **extra):
    selection={'episode_ids':[ep]}
    preview=client.post(root+'/sharing/preview',headers=oh,json=selection)
    assert preview.status_code==200,preview.text
    p=preview.json()
    assert p['items'][0]['transcript'] and p['includes_full_audio'] is True
    response=client.post(root+'/invitations',headers=oh,json={**selection,
        'source_version':p['source_version'],'include_audio_confirmed':True,
        'cloud_processing_allowed':True,**extra})
    assert response.status_code==201,response.text
    return response.json(),p


def claim(client,rh,code):
    return client.post('/api/v1/workbench/invitations/claim',headers=rh,json={'code':code})


def test_claim_requires_owner_confirmation_and_revoke_blocks_audio(app,client,session):
    owner,reader,oh,rh,ep,root=prepare(app,client,session)
    invitation,p=invite(client,oh,root,ep)
    path=root+'/invitations/'+invitation['id']
    assert client.get(root+'/stories',headers=rh).status_code==404
    claimed=claim(client,rh,invitation['code'])
    assert claimed.status_code==200,claimed.text
    assert claimed.json()['status']=='claimed'
    assert 'episode_ids' not in claimed.json() and 'transcript' not in str(claimed.json())
    assert client.get(root+'/stories',headers=rh).status_code==404
    assert client.get(root+'/invitations',headers=rh).status_code==404
    listed=client.get(root+'/invitations',headers=oh).json()['items'][0]
    assert listed['recipient']['username']=='reader_one'
    assert [item['episode_id'] for item in listed['scope']]==[ep]
    assert listed['scope'][0]['title'] and listed['scope'][0]['recorded_at']
    assert invitation['code'] not in str(listed)
    approved=client.post(path+'/approve',headers=oh)
    assert approved.status_code==200,approved.text
    grants=approved.json()['grant_ids']; assert len(grants)==1
    assert client.post(path+'/approve',headers=oh).json()['grant_ids']==grants
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==200
    assert client.post(path+'/revoke',headers=oh).status_code==200
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==404
    assert client.post(path+'/approve',headers=oh).status_code==422


@pytest.mark.parametrize('action',['reject','cancel'])
def test_owner_can_stop_claimed_invitation(app,client,session,action):
    *_,oh,rh,ep,root=prepare(app,client,session)
    invitation,_=invite(client,oh,root,ep); claim(client,rh,invitation['code'])
    path=root+'/invitations/'+invitation['id']
    assert client.post(path+'/'+action,headers=rh).status_code==404
    assert client.post(path+'/'+action,headers=oh).status_code==200
    assert claim(client,rh,invitation['code']).status_code==422
    assert client.post(path+'/approve',headers=oh).status_code==422


def test_expired_code_self_claim_and_other_claimant(app,client,session):
    from app.models import ShareInvitation
    *_,oh,rh,ep,root=prepare(app,client,session)
    invitation,_=invite(client,oh,root,ep)
    assert claim(client,oh,invitation['code']).status_code==422
    assert claim(client,rh,invitation['code']).status_code==200
    assert claim(client,rh,invitation['code']).status_code==200
    other=client.post('/api/v1/accounts/register',json={'username':'other_reader','password':'long-test-password','display_name':'另一个读者'}).json()
    assert claim(client,{'Authorization':'Bearer '+other['actor_token']},invitation['code']).status_code==422
    session.get(ShareInvitation,invitation['id']).expires_at=utcnow()-timedelta(seconds=1);session.commit()
    assert client.post(root+'/invitations/'+invitation['id']+'/approve',headers=oh).status_code==422
    assert client.get(root+'/invitations',headers=oh).json()['items'][0]['status']=='expired'


def test_changed_preview_and_approval_are_rejected_without_partial_grants(app,client,session):
    *_,oh,rh,ep,root=prepare(app,client,session)
    invitation,p=invite(client,oh,root,ep);claim(client,rh,invitation['code'])
    session.get(Episode,ep).transcript+=' 新补充';session.commit()
    stale=client.post(root+'/invitations',headers=oh,json={'episode_ids':[ep],
        'source_version':p['source_version'],'include_audio_confirmed':True})
    assert stale.status_code==409,stale.text
    approved=client.post(root+'/invitations/'+invitation['id']+'/approve',headers=oh)
    assert approved.status_code==409,approved.text
    session.expire_all(); assert list(session.scalars(select(StoryGrant)))==[]


def test_existing_grants_survive_batch_revocation_and_contacts_can_be_reused(app,client,session):
    owner,reader,oh,rh,ep,root=prepare(app,client,session)
    old=client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,
        'include_audio_confirmed':True,'cloud_processing_allowed':True}).json()
    invitation,_=invite(client,oh,root,ep);claim(client,rh,invitation['code'])
    path=root+'/invitations/'+invitation['id']
    assert client.post(path+'/approve',headers=oh).status_code==200
    contacts=client.get(root+'/recipients',headers=oh).json()['items']
    assert contacts[0]['username']=='reader_one'
    assert client.post(path+'/revoke',headers=oh).status_code==200
    session.expire_all(); assert session.get(StoryGrant,old['grant_id']).revoked_at is None
    next_invite,_=invite(client,oh,root,ep,recipient_actor_id=reader.actor_id)
    assert 'code' not in next_invite and next_invite['status']=='claimed'
    assert client.post(root+'/invitations/'+next_invite['id']+'/approve',headers=oh).status_code==200


def test_unconfirmed_contact_cannot_skip_claim_and_cloud_permission_separate(app,client,session):
    owner,reader,oh,rh,ep,root=prepare(app,client,session)
    p=client.post(root+'/sharing/preview',headers=oh,json={'episode_ids':[ep]}).json()
    response=client.post(root+'/invitations',headers=oh,json={'episode_ids':[ep],
        'source_version':p['source_version'],'include_audio_confirmed':True,'recipient_actor_id':reader.actor_id})
    assert response.status_code==422
    invitation,_=invite(client,oh,root,ep,cloud_processing_allowed=False);claim(client,rh,invitation['code'])
    approved=client.post(root+'/invitations/'+invitation['id']+'/approve',headers=oh).json()
    assert client.get(root+f'/stories/{ep}/audio',headers=rh).status_code==200
    response=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=rh,
        json={'question':'喜欢什么？','cloud_consent_id':approved['grant_ids'][0]})
    assert response.status_code==404


def test_service_info_is_available_before_login_without_secrets(app,client):
    app.state.settings.allow_account_registration=False
    response=client.get('/api/v1/service-info')
    assert response.status_code==200
    assert response.json()['registration_allowed'] is False
    assert response.json()['sharing_invitations'] is True
    assert 'api_key' not in response.text and 'database_url' not in response.text


def test_story_preview_expands_all_recordings_and_refuses_partial_invalid_batch(app,client,session):
    from app.materials import effective_materials
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,root=prepare(app,client,session)
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    second=_record(client,app,owner.subject_id,owner.consent_id,oh)
    sources=effective_materials(session,owner.subject_id,{ep,second});session.commit()
    ids=list(dict.fromkeys(e['evidence_id'] for m in sources for e in m['evidence']))
    row=client.post(root+'/narrative/records',headers=oh,json={'kind':'story','title':'两段共同讲述','text':'一件事的补充',
        'evidence_ids':ids,'facets':['EXPERIENCE']}).json()
    client.post(root+'/narrative/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    preview=client.post(root+'/sharing/preview',headers=oh,json={'story_ids':[row['id']]})
    assert preview.status_code==200,preview.text
    assert set(preview.json()['episode_ids'])=={ep,second}
    assert len(preview.json()['items'])==2
    # Existing cloud-disabled grant must cause the whole two-recording approval to fail.
    client.post(root+'/grants',headers=oh,json={'episode_id':second,'reader_actor_id':reader.actor_id,
        'include_audio_confirmed':True,'cloud_processing_allowed':False})
    inv=client.post(root+'/invitations',headers=oh,json={'story_ids':[row['id']],
        'source_version':preview.json()['source_version'],'include_audio_confirmed':True,'cloud_processing_allowed':True}).json()
    assert {item['episode_id'] for item in inv['scope']}=={ep,second}
    claim(client,rh,inv['code'])
    assert client.post(root+'/invitations/'+inv['id']+'/approve',headers=oh).status_code==422
    session.expire_all()
    assert list(session.scalars(select(StoryGrant.episode_id)))==[second]


def test_concurrent_claimers_cannot_both_bind_same_code(app,client,session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    *_,oh,rh,ep,root=prepare(app,client,session)
    other=client.post('/api/v1/accounts/register',json={'username':'another_reader','password':'long-test-password','display_name':'另一个读者'}).json()
    invitation,_=invite(client,oh,root,ep);gate=Barrier(2)
    def run(headers):
        with TestClient(app) as c:
            gate.wait(timeout=10)
            return claim(c,headers,invitation['code']).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,[rh,{'Authorization':'Bearer '+other['actor_token']}]))
    assert sorted(results)==[200,422]


def test_concurrent_approval_is_atomic_and_idempotent(app,client,session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    *_,oh,rh,ep,root=prepare(app,client,session)
    invitation,_=invite(client,oh,root,ep);claim(client,rh,invitation['code']);barrier=Barrier(2)
    def approve(_):
        with TestClient(app) as other:
            barrier.wait(timeout=10)
            response=other.post(root+'/invitations/'+invitation['id']+'/approve',headers=oh)
            assert response.status_code==200,response.text
            return response.json()['grant_ids']
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(approve,range(2)))
    assert results[0]==results[1]
    session.expire_all();assert len(list(session.scalars(select(StoryGrant))))==1
