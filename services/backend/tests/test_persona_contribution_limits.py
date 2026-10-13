"""The public dialogue route rejects oversized context before any provider call."""
import pytest
from app.models import TwinAnswer
from test_reader_understandings import prepare, candidate, confirm
from test_persona_dialogue import PersonaSpy, enable, cloud
from test_companion import permission, post


def setup(app,client,session):
    owner,author,oh,ah,ep,_,source,_,root=prepare(app,client,session)
    row=candidate(session,owner,[source]);confirm(client,root,oh,row);enable(client,root,oh,source)
    consent=cloud(client,owner.subject_id,oh)
    app.state.settings.ai_backend='http';spy=PersonaSpy();app.state.twin_client=spy
    companion=root+'/companion';permission(client,companion,oh,author)
    return owner,oh,ah,companion,consent,spy


def add_allowed(client,root,oh,ah,key,text):
    note=post(client,root+'/contributions',ah,{'idempotency_key':key,'classification':'opinion','text':text},201)
    path=root+'/contributions/'+note['id']
    note=post(client,path+'/review',oh,{'revision':note['revision'],'decision':'accepted'})
    for headers in (oh,ah):
        response=client.put(path+'/model-use',headers=headers,json={'revision':note['revision'],'allowed':True})
        assert response.status_code==200,response.text
        note=response.json()
    return note


def test_five_thousand_character_note_is_saved_and_forwarded_whole(app,client,session):
    owner,oh,ah,root,consent,spy=setup(app,client,session)
    text='亲'*5000
    note=add_allowed(client,root,oh,ah,'full-note',text)
    result=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'怎么考虑','cloud_consent_id':consent,'mode':'persona'})
    assert result.status_code==200,result.text
    assert spy.payload['contributions'][0]['text']==text
    assert client.get(root+'/contributions/'+note['id'],headers=ah).json()['text']==text


@pytest.mark.parametrize('kind',['characters','count'])
def test_oversized_contribution_context_fails_before_model_without_truncating_notes(app,client,session,kind):
    owner,oh,ah,root,consent,spy=setup(app,client,session)
    lengths=[3000,3000] if kind=='characters' else [10]*17
    notes=[add_allowed(client,root,oh,ah,'note-'+str(i),'亲'*n) for i,n in enumerate(lengths)]
    result=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'怎么考虑','cloud_consent_id':consent,'mode':'persona'})
    assert result.status_code==413,result.text
    assert result.json()['error_code']=='CONTEXT_TOO_LARGE'
    assert ('6000' if kind=='characters' else '16') in result.json()['error_message']
    assert spy.payload is None
    assert session.query(TwinAnswer).count()==0
    for note,n in zip(notes,lengths):
        assert client.get(root+'/contributions/'+note['id'],headers=ah).json()['text']=='亲'*n
