import pytest
from sqlalchemy import select,func
from app.models import Episode,PersonTrait,ModelRevision,utcnow
from app.entrust_models import Entrustment,EntrustUnlock,LegacyState
from app.seed import seed_development_data
from app.api.entrustments import hash_secret,verify_secret
from test_twin_voice import _record,TinyEncoder

class ScopedTwin:
    def __init__(self,callback=None):self.calls=[];self.callback=callback
    def answer(self,question,candidates,**kwargs):
        self.calls.append((question,candidates,kwargs))
        if self.callback:self.callback()
        if candidates:
            ev=candidates[0]['evidence'][0]
            return {'answer':ev['excerpt'],'response_type':'ORIGINAL','evidence_ids':[ev['evidence_id']],'confidence':.9,'model_version':'fixture'}
        return {'answer':'还没有这方面的资料。','response_type':'CONVERSATION','evidence_ids':[],'confidence':0,'model_version':'fixture'}

@pytest.fixture
def plans(app,client,session):
    own=seed_development_data(session,subject_name='Owner',actor_name='Owner')
    visitor=seed_development_data(session,subject_name='Visitor',actor_name='Visitor')
    third=seed_development_data(session,subject_name='Other',actor_name='Other')
    h={'Authorization':'Bearer '+own.actor_token};v={'Authorization':'Bearer '+visitor.actor_token};t={'Authorization':'Bearer '+third.actor_token}
    ep=_record(client,app,own.subject_id,own.consent_id,h)
    grant=client.post('/api/v1/consents',headers=h,json={'subject_id':own.subject_id,'scope':'DIGITAL_HANDOVER'}).json()['consent_id']
    body={'recipient_actor_id':visitor.actor_id,'recipient_label':'小王','episode_ids':[ep],'secret':'我们的秘密句子','handover_consent_id':grant}
    r=client.post('/api/v1/subjects/'+own.subject_id+'/entrustments',headers=h,json=body);assert r.status_code==200,r.text
    plan=r.json()['plan_id'];app.state.embedding_encoder=TinyEncoder();app.state.twin_client=ScopedTwin();app.state.settings.ai_backend='http'
    return own,visitor,third,h,v,t,ep,grant,body,plan

def open_plan(client,plan,headers):
    visit=client.post('/api/v1/entrustments/'+plan+'/start',headers=headers);assert visit.status_code==200,visit.text
    v={**headers,'X-Entrust-Visit':visit.json()['visit_id']}
    result=client.post('/api/v1/entrustments/'+plan+'/unlock',headers=v,json={'phrase':'我们的秘密句子。'})
    assert result.status_code==200,result.text
    return {**headers,'X-Entrust-Unlock':result.json()['unlock_token']},v

def test_secret_hash_and_voice_punctuation_do_not_replace_account_or_grant(client,session,plans):
    own,visitor,third,h,v,t,ep,grant,body,plan=plans
    digest=session.get(Entrustment,plan).secret_hash
    assert '秘密' not in digest and verify_secret('我们的秘密句子。',digest)
    assert not verify_secret('另一个句子',digest)
    for headers in (h,t):
        r=client.post('/api/v1/entrustments/'+plan+'/unlock',headers=headers,json={'phrase':'我们的秘密句子'})
        assert r.status_code==404
    assert client.post('/api/v1/entrustments/'+plan+'/questions',headers=v,json={'question':'你记得吗','request_id':'r'}).status_code==404

def test_recipient_scope_does_not_grant_ordinary_reader_access_or_update_model(app,client,session,plans):
    own,visitor,third,h,v,t,ep,grant,body,plan=plans
    session.expire_all();before=session.get(ModelRevision,own.subject_id).version
    uh,_=open_plan(client,plan,v)
    result=client.post('/api/v1/entrustments/'+plan+'/questions',headers=uh,json={'question':'你喜欢什么','request_id':'first'})
    assert result.status_code==200,result.text
    assert result.json()['answer']=='我喜欢散步'
    call=app.state.twin_client.calls[0];assert {e['episode_id'] for c in call[1] for e in c['evidence']}=={ep}
    assert call[2]['conversation_turns']==[] and 'conversation_recall' not in call[2]
    assert client.get('/api/v1/subjects/'+own.subject_id+'/memory-search?q=散步',headers=v).status_code==404
    again=client.post('/api/v1/entrustments/'+plan+'/questions',headers=uh,json={'question':'那后来呢','request_id':'second','previous_answer_id':result.json()['answer_id']})
    assert again.status_code==200,again.text
    session.expire_all();assert session.get(ModelRevision,own.subject_id).version==before
    assert session.scalar(select(func.count()).select_from(Episode).where(Episode.subject_id==own.subject_id))==1

def test_two_unlocks_cannot_mix_parent_chains_and_revoke_denies_late_answer(app,client,session,plans):
    own,visitor,third,h,v,t,ep,grant,body,plan=plans
    a,_=open_plan(client,plan,v)
    first=client.post('/api/v1/entrustments/'+plan+'/questions',headers=a,json={'question':'之前说过什么','request_id':'one'});assert first.status_code==200,first.text
    b,_=open_plan(client,plan,v)
    assert client.post('/api/v1/entrustments/'+plan+'/questions',headers=b,json={'question':'再聊聊','request_id':'two','previous_answer_id':first.json()['answer_id']}).status_code==404
    app.state.twin_client=ScopedTwin(callback=lambda:client.post('/api/v1/entrustments/'+plan+'/revoke',headers=h))
    r=client.post('/api/v1/entrustments/'+plan+'/questions',headers=b,json={'question':'在撤权时回答','request_id':'late'})
    assert r.status_code==404,r.text
    assert client.get('/api/v1/entrustments/'+plan+'/status',headers=b).status_code==404

def test_inactive_future_plan_requires_designated_human_transition_and_freezes_new_person_input(app,client,session,plans):
    own,visitor,third,h,v,t,ep,grant,body,plan=plans
    route='/api/v1/subjects/'+own.subject_id+'/legacy'
    assert client.put(route+'/steward',headers=h,json={'steward_actor_id':third.actor_id}).status_code==200
    r=client.post('/api/v1/subjects/'+own.subject_id+'/entrustments',headers=h,json={**body,'condition':'after_verified_transition'});future=r.json()['plan_id']
    assert client.post('/api/v1/entrustments/'+future+'/start',headers=v).status_code==404
    assert client.post(route+'/verify',headers=v,json={'verification_ref':'attestation-fixture','verified':True}).status_code==404
    assert client.post(route+'/verify',headers=t,json={'verification_ref':'attestation-fixture','verified':True}).status_code==200
    uh,_=open_plan(client,future,v)
    assert client.get('/api/v1/entrustments/'+future+'/status',headers=uh).status_code==200
    session.expire_all();state=session.get(LegacyState,own.subject_id);before=state.baseline['person_model_version']
    from app.repositories.person_model import PersonModelRepository
    assert PersonModelRepository(session).rebuild(own.subject_id,include_episode_id='new-after-transition')==before
    assert client.post(route+'/verify',headers=t,json={'verification_ref':'disputed-fixture','verified':False}).status_code==200
    assert client.get('/api/v1/entrustments/'+future+'/status',headers=uh).status_code==404

def test_five_wrong_phrases_throttle_without_disclosing_other_plans(client,plans):
    own,visitor,third,h,v,t,ep,grant,body,plan=plans
    visit=client.post('/api/v1/entrustments/'+plan+'/start',headers=v).json()['visit_id'];vh={**v,'X-Entrust-Visit':visit}
    for _ in range(5):assert client.post('/api/v1/entrustments/'+plan+'/unlock',headers=vh,json={'phrase':'这是错误的密语'}).status_code==404
    assert client.post('/api/v1/entrustments/'+plan+'/unlock',headers=vh,json={'phrase':'我们的秘密句子'}).status_code==404
    assert client.get('/api/v1/entrustments',headers=t).json()['items']==[]
