"""Coverage is persisted separately from source validity, without reviewer prose."""
import pytest
from sqlalchemy import select
from app.models import TwinAnswer, Episode
from test_persona_dialogue import PersonaSpy, enable, cloud
from test_reader_understandings import prepare, candidate, confirm


def context(app,client,session,summary):
    owner,_,oh,_,ep,_,source,_,root=prepare(app,client,session)
    row=candidate(session,owner,[source]);confirm(client,root,oh,row)
    enable(client,root,oh,source)
    consent=cloud(client,owner.subject_id,oh)
    class Reviewed(PersonaSpy):
        def persona(self,payload):
            return dict(super().persona(payload),**summary)
    app.state.settings.ai_backend='http';app.state.twin_client=Reviewed()
    return owner,oh,ep,f'/api/v1/subjects/{owner.subject_id}/twin/answers',{
        'question':'这次会怎么考虑？还有没有别的计划？',
        'mode':'persona','cloud_consent_id':consent}


def test_partial_answer_coverage_survives_readback_without_reasoning(app,client,session):
    _,oh,_,path,body=context(app,client,session,{'coverage':'partial','omitted_points':1})
    response=client.post(path,headers=oh,json=body)
    assert response.status_code==200,response.text
    row=response.json()
    assert row['coverage']=='partial' and row['omitted_points']==1
    read=client.get(path+'/'+row['answer_id'],headers=oh)
    assert read.status_code==200
    assert read.json()['coverage']=='partial' and read.json()['omitted_points']==1
    assert read.json()['answer']==row['answer']
    assert 'reasoning' not in read.json()


@pytest.mark.parametrize('summary',[
    {'coverage':'complete','omitted_points':1},
    {'coverage':'excellent','omitted_points':0},
    {'coverage':'partial','omitted_points':True},
    {'coverage':'partial','omitted_points':-1},
    {'coverage':'partial','omitted_points':5},
    {'coverage':'partial'},
    {'omitted_points':0},
])
def test_invalid_coverage_does_not_publish_answer(app,client,session,summary):
    _,oh,_,path,body=context(app,client,session,summary)
    response=client.post(path,headers=oh,json=body)
    assert response.status_code==503,response.text
    assert list(session.scalars(select(TwinAnswer)))==[]


def test_source_change_hides_saved_coverage_with_answer(app,client,session):
    _,oh,ep,path,body=context(app,client,session,{'coverage':'complete','omitted_points':0})
    row=client.post(path,headers=oh,json=body).json()
    session.get(Episode,ep).transcript+='。后来有新说明';session.commit()
    response=client.get(path+'/'+row['answer_id'],headers=oh)
    assert response.status_code==200,response.text
    assert response.json()['stale'] is True
    assert response.json()['coverage'] is None
    assert response.json()['omitted_points'] is None


def test_older_worker_results_are_not_relabelled_complete(app,client,session):
    _,oh,_,path,body=context(app,client,session,{})
    response=client.post(path,headers=oh,json=body)
    assert response.status_code==200,response.text
    assert response.json()['coverage'] is None
    assert response.json()['omitted_points'] is None


@pytest.mark.parametrize('extra',[
    {'omitted_points':1},
    {'understanding_ids':['should-not-exist']},
    {'contribution_ids':['should-not-exist']},
    {'evidence_ids':['should-not-exist']},
])
def test_unknown_cannot_hide_removed_known_claims_or_keep_known_references(app,client,session,extra):
    _,oh,_,path,body=context(app,client,session,dict(
        response_type='UNKNOWN',answer='不知道',evidence_ids=[],understanding_ids=[],contribution_ids=[],
        coverage='partial',omitted_points=0,**{}))
    spy=app.state.twin_client
    original=spy.persona
    spy.persona=lambda payload:dict(original(payload),**extra)
    response=client.post(path,headers=oh,json=body)
    assert response.status_code==503,response.text
    assert list(session.scalars(select(TwinAnswer)))==[]
