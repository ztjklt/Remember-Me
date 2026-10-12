"""Persona context is subject to the same full-source gates as the person page."""
from sqlalchemy import select
from app.models import TwinAnswer, MemoryItem
from test_reader_understandings import prepare, candidate, confirm, grant


class PersonaSpy:
    def __init__(self, callback=None): self.payload=None; self.callback=callback
    def persona(self, payload):
        self.payload=payload
        if self.callback: self.callback()
        trait=payload['understandings'][0]
        return dict(answer='我平时会省着花，但也会看看这次具体需要什么。',response_type='SIMULATION',
            evidence_ids=trait['evidence_ids']+trait['counter_evidence_ids'],confidence=.7,
            model_version='fixture-persona',understanding_ids=[trait['id']],contribution_ids=[],prompt_version='persona-v1')


def enable(client, root, oh, source):
    response=client.post(root+'/narrative/records',headers=oh,json={
        'kind':'style','title':'说话例子','text':source['excerpt'],'facets':['EXPRESSION'],
        'evidence_ids':[source['evidence_id']]})
    assert response.status_code==201,response.text
    row=response.json()
    assert client.post(root+'/narrative/records/'+row['id']+'/confirm',headers=oh,json={'revision':row['revision']}).status_code==200
    response=client.put(root+'/narrative/style',headers=oh,json={'revision':0,'enabled':True})
    assert response.status_code==200,response.text


def cloud(client,subject,oh):
    return client.post('/api/v1/consents',headers=oh,json={'subject_id':subject,'scope':'CLOUD_TWIN'}).json()['consent_id']


def test_persona_uses_same_confirmed_context_for_reader_and_owner(app,client,session):
    o,r,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    row=candidate(session,o,[source],[extra]);confirm(client,root,oh,row)
    enable(client,root,oh,source)
    g=grant(client,root,oh,r,ep);grant(client,root,oh,r,other)
    # Reading grants need explicit cloud permission, as in the normal question UI.
    from app.models import StoryGrant
    for g0 in session.scalars(select(StoryGrant)): g0.cloud_processing_allowed=True
    session.commit()
    app.state.settings.ai_backend='http';spy=PersonaSpy();app.state.twin_client=spy
    path=f'/api/v1/subjects/{o.subject_id}/twin/answers'
    result=client.post(path,headers=rh,json={'question':'遇到新的开支会怎么考虑？','cloud_consent_id':g['grant_id'],'mode':'persona'})
    assert result.status_code==200,result.text
    assert spy.payload['understandings'][0]['counter_evidence_ids']==[extra['evidence_id']]
    assert result.json()['mode']=='persona'
    assert result.json()['understanding_ids']==[row.candidate_id]
    assert len(list(session.scalars(select(TwinAnswer))))==1


def test_persona_disabled_or_incomplete_counter_source_never_calls_model(app,client,session):
    o,r,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    row=candidate(session,o,[source],[extra]);confirm(client,root,oh,row)
    c=cloud(client,o.subject_id,oh);spy=PersonaSpy();app.state.twin_client=spy;app.state.settings.ai_backend='http'
    path=f'/api/v1/subjects/{o.subject_id}/twin/answers'
    assert client.post(path,headers=oh,json={'question':'怎么考虑','cloud_consent_id':c,'mode':'persona'}).status_code==422
    assert spy.payload is None
    enable(client,root,oh,source);g=grant(client,root,oh,r,ep)
    from app.models import StoryGrant
    session.get(StoryGrant,g['grant_id']).cloud_processing_allowed=True;session.commit()
    response=client.post(path,headers=rh,json={'question':'怎么考虑','cloud_consent_id':g['grant_id'],'mode':'persona'})
    assert response.status_code==422,response.text
    assert spy.payload is None


def test_style_disable_during_generation_does_not_publish_old_persona(app,client,session):
    o,r,oh,rh,ep,_,source,_,root=prepare(app,client,session)
    row=candidate(session,o,[source]);confirm(client,root,oh,row);enable(client,root,oh,source)
    c=cloud(client,o.subject_id,oh)
    def disable():
        assert client.put(root+'/narrative/style',headers=oh,json={'revision':1,'enabled':False}).status_code==200
    app.state.settings.ai_backend='http';app.state.twin_client=PersonaSpy(disable)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,
        json={'question':'怎么考虑','cloud_consent_id':c,'mode':'persona'})
    assert response.status_code==409,response.text
    assert list(session.scalars(select(TwinAnswer)))==[]


def test_contribution_withdrawal_during_generation_three_cycles(app,client,session):
    o,r,oh,rh,ep,_,source,_,root=prepare(app,client,session)
    row=candidate(session,o,[source]);confirm(client,root,oh,row);enable(client,root,oh,source)
    c=cloud(client,o.subject_id,oh);companion=root+'/companion'
    assert client.put(companion+'/contribution-grants/'+r.actor_id,headers=oh,
        json={'revision':0,'enabled':True}).status_code==200
    baseline=session.query(MemoryItem).count()
    for cycle in range(3):
        note=client.post(companion+'/contributions',headers=rh,json={
            'idempotency_key':f'withdrawal-race-{cycle}','classification':'opinion',
            'text':'我觉得他愿意听我说完，这是我的个人看法。'}).json()
        path=companion+'/contributions/'+note['id']
        note=client.post(path+'/review',headers=oh,json={'revision':note['revision'],'decision':'accepted'}).json()
        for h in (oh,rh):
            reply=client.put(path+'/model-use',headers=h,json={'revision':note['revision'],'allowed':True})
            assert reply.status_code==200,reply.text
            note=reply.json()
        class ContributionTwin:
            def persona(self,payload):
                assert [n['id'] for n in payload['contributions']]==[note['id']]
                revoked=client.post(path+'/withdraw',headers=rh,json={'revision':note['revision']})
                assert revoked.status_code==200,revoked.text
                return dict(answer='读者的个人看法：他愿意听对方说完。',response_type='SIMULATION',
                    evidence_ids=[],confidence=.6,model_version='fixture-persona',
                    understanding_ids=[],contribution_ids=[note['id']],prompt_version='fixture')
        app.state.settings.ai_backend='http';app.state.twin_client=ContributionTwin()
        response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,
            json={'question':'亲友怎么看他？','cloud_consent_id':c,'mode':'persona'})
        assert response.status_code==409,response.text
        assert list(session.scalars(select(TwinAnswer)))==[]
        assert session.query(MemoryItem).count()==baseline
