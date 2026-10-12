"""RAG selection must preserve the same source/permission gates as full context."""
import pytest
from sqlalchemy import select
from app.models import Episode, TwinAnswer, StoryGrant
from app.rag_contract import RagResult, RagHit
from test_persona_dialogue import PersonaSpy, enable, cloud
from test_reader_understandings import prepare, candidate, confirm, grant


def setup(app,client,session):
    o,r,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    row=candidate(session,o,[source],[extra]);confirm(client,root,oh,row)
    enable(client,root,oh,source)
    spy=PersonaSpy();app.state.twin_client=spy;app.state.settings.ai_backend='http'
    return o,r,oh,rh,ep,other,source,extra,root,spy


def provider(monkeypatch, source, callback=None):
    class Picker:
        seen=None
        def retrieve(self,request):
            self.seen=request
            ref=next(x for x in request.authorized_evidence if x.evidence_id==source['evidence_id'])
            if callback: callback()
            return RagResult(hits=(RagHit(evidence_id=ref.evidence_id,fingerprint=ref.fingerprint,score=1.0),),retriever_version='test-picker')
    picker=Picker()
    monkeypatch.setattr('app.api.twin.build_rag_provider',lambda *a,**kw:picker)
    return picker


def test_selected_support_expands_counterexample_before_persona(app,client,session,monkeypatch):
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    picker=provider(monkeypatch,source)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'这次会怎么考虑？','mode':'persona','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==200,response.text
    ids={e['evidence_id'] for c in spy.payload['candidates'] for e in c['evidence']}
    assert {source['evidence_id'],extra['evidence_id']}<=ids
    assert spy.payload['understandings'][0]['counter_evidence_ids']==[extra['evidence_id']]
    assert picker.seen is not None
    assert 'excerpt' not in picker.seen.model_dump_json()
    from app.persona_models import PersonaAnswerContext
    audit=session.get(PersonaAnswerContext,response.json()['answer_id']).review_summary['retrieval']
    assert audit['mode']=='local' and audit['retriever_version']=='test-picker'
    assert {source['evidence_id'],extra['evidence_id']}<=set(audit['selected_evidence_ids'])
    assert audit['source_basis']==response.json()['source_version']


def test_default_full_path_does_not_call_rag_provider(app,client,session,monkeypatch):
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    picker=provider(monkeypatch,source)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'怎么考虑？','mode':'persona','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==200,response.text
    assert picker.seen is None


def test_modification_during_retrieval_prevents_model_call(app,client,session,monkeypatch):
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    def modify():
        session.get(Episode,ep).transcript+='。有新说明';session.commit()
    provider(monkeypatch,source,modify)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'怎么考虑？','mode':'persona','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==409,response.text
    assert spy.payload is None and not list(session.scalars(select(TwinAnswer)))


def test_reader_retrieval_never_receives_private_source(app,client,session,monkeypatch):
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    g=grant(client,root,oh,r,ep)
    session.get(StoryGrant,g['grant_id']).cloud_processing_allowed=True;session.commit()
    picker=provider(monkeypatch,source)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=rh,json={
        'question':'怎么考虑？','mode':'persona','retrieval_mode':'local','cloud_consent_id':g['grant_id']})
    # Persona is unavailable because its counterexample is not shared.
    assert response.status_code==422,response.text
    assert extra['evidence_id'] not in {e.evidence_id for e in picker.seen.authorized_evidence}
    assert spy.payload is None


def test_old_event_selection_also_carries_later_change(app,client,session,monkeypatch):
    from app.models import MemoryRevision, MemoryItem
    o,r,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.add(MemoryRevision(revision_id='rag-later-change',subject_id=o.subject_id,
        target_memory_id=old.memory_item_id,episode_id=other,kind='change',time_text='后来',status='confirmed'))
    session.commit()
    picker=provider(monkeypatch,source)
    class Capture:
        payload=None
        def answer(self,q,rows):
            self.payload=rows
            return dict(answer='现有记录还不足以确定。',response_type='UNKNOWN',evidence_ids=[],confidence=0,model_version='test')
    spy=Capture();app.state.twin_client=spy;app.state.settings.ai_backend='http'
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'过去和后来有什么不同？','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==200,response.text
    assert {source['evidence_id'],extra['evidence_id']} <= {e['evidence_id'] for c in spy.payload for e in c['evidence']}


def test_legitimate_empty_rag_is_not_misreported_as_persona_not_enabled(app,client,session,monkeypatch):
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    class Empty:
        def retrieve(self,request):return RagResult(hits=(),retriever_version='empty-test')
    monkeypatch.setattr('app.api.twin.build_rag_provider',lambda *a,**kw:Empty())
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'还没讲过的地点？','mode':'persona','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==200,response.text
    assert response.json()['response_type']=='UNKNOWN' and response.json()['evidence']==[]
    assert spy.payload is None
