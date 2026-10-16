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


def test_local_vectors_survive_fresh_authorization_snapshot(app,client,session):
    """Regression: publication_lock used to roll back every new embedding."""
    from types import SimpleNamespace
    from app.api.twin import TwinQuestion, generate_answer
    from app.models import MemoryEmbedding
    from test_twin_voice import TinyEncoder
    o,_,oh,_,_,_,_,_,_=prepare(app,client,session)
    class CountingEncoder(TinyEncoder):
        def __init__(self):self.calls=[]
        def encode(self,texts):self.calls.append(list(texts));return super().encode(texts)
    encoder=CountingEncoder();app.state.embedding_encoder=encoder
    question=TwinQuestion(question='喜欢散步吗？',retrieval_mode='local',cloud_consent_id=cloud(client,o.subject_id,oh))
    first=generate_answer(o.subject_id,question,SimpleNamespace(app=app),o,session,context_only=True)
    assert session.scalars(select(MemoryEmbedding)).all(), 'Fresh snapshot rolled back the vector cache'
    before=len(encoder.calls)
    second=generate_answer(o.subject_id,question,SimpleNamespace(app=app),o,session,context_only=True)
    assert len(encoder.calls)==before+1, 'Unchanged archive was embedded again'
    assert encoder.calls[-1]==[question.question]
    assert first['candidates']==second['candidates'] and first['source_version']==second['source_version']


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


def test_context_only_keeps_counterexample_without_model_or_answer_write(app,client,session,monkeypatch):
    from types import SimpleNamespace
    from app.api.twin import TwinQuestion, generate_answer
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    provider(monkeypatch,source)
    packet=generate_answer(o.subject_id,TwinQuestion(question='这次怎么考虑？',mode='persona',
        retrieval_mode='local',cloud_consent_id=cloud(client,o.subject_id,oh)),
        SimpleNamespace(app=app),o,session,context_only=True)
    ids={e['evidence_id'] for c in packet['candidates'] for e in c['evidence']}
    assert {source['evidence_id'],extra['evidence_id']}<=ids
    assert packet['understandings'][0]['counter_evidence_ids']==[extra['evidence_id']]
    assert spy.payload is None and not list(session.scalars(select(TwinAnswer)))


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


def test_unchanged_rag_snapshot_does_not_rebuild_whole_archive(app,client,session,monkeypatch):
    """Repeated permission/version checks must not repeatedly expand the archive."""
    import app.api.twin as twin
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    provider(monkeypatch,source)
    original=twin.effective_materials; expansions=[]
    def material(*args,**kwargs):
        result=original(*args,**kwargs);expansions.append(result);return result
    monkeypatch.setattr(twin,'effective_materials',material)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'这次会怎么考虑？','mode':'persona','retrieval_mode':'local',
        'cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==200,response.text
    assert len(expansions)==1
    assert spy.payload['understandings'][0]['counter_evidence_ids']==[extra['evidence_id']]


def test_call_material_cache_reuses_only_unchanged_authorized_sources(app,client,session,monkeypatch):
    import app.api.twin as twin
    from app.voice_material_cache import VoiceMaterialCache
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    provider(monkeypatch,source)
    cache=VoiceMaterialCache();original=twin.generate_answer;expansions=[]
    material=twin.effective_materials
    def count(*a,**kw):expansions.append(1);return material(*a,**kw)
    monkeypatch.setattr(twin,'effective_materials',count)
    monkeypatch.setattr(twin,'generate_answer',lambda *a,**kw:original(*a,**kw,material_cache=cache))
    body={'question':'这次会怎么考虑？','mode':'persona','retrieval_mode':'local',
          'cloud_consent_id':cloud(client,o.subject_id,oh)}
    path=f'/api/v1/subjects/{o.subject_id}/twin/answers'
    for _ in range(2):
        response=client.post(path,headers=oh,json=body)
        assert response.status_code==200,response.text
    assert len(expansions)==1
    # This change invalidates prior provenance, so no prior profile may survive.
    session.get(Episode,ep).transcript+='。后来我补充了一件新事。';session.commit()
    response=client.post(path,headers=oh,json=body)
    assert len(expansions)==2
    assert response.status_code in {200,409,422}


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


def test_prefetch_publishes_nothing_then_reuses_only_exact_final_query(app,client,session,monkeypatch):
    import app.api.twin as twin
    from app.voice_material_cache import VoiceMaterialCache
    from app.voice_prefetch import SelectionCache
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    picker=provider(monkeypatch,source);retrieved=[];old=picker.retrieve
    def counted(q):retrieved.append(q);return old(q)
    picker.retrieve=counted
    m=VoiceMaterialCache();c=SelectionCache();original=twin.generate_answer
    phase={'prepare':True}
    def invoke(*a,**kw):return original(*a,**kw,material_cache=m,selection_cache=c,prepare_only=phase['prepare'])
    monkeypatch.setattr(twin,'generate_answer',invoke)
    body={'question':'这次会怎么考虑？','mode':'persona','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)}
    path=f'/api/v1/subjects/{o.subject_id}/twin/answers'
    result=client.post(path,headers=oh,json=body)
    assert result.status_code==200,result.text
    assert result.json()['prepared'] is True and spy.payload is None
    assert not list(session.scalars(select(TwinAnswer)))
    phase['prepare']=False
    assert client.post(path,headers=oh,json=body).status_code==200
    assert len(retrieved)==1
    assert {source['evidence_id'],extra['evidence_id']}<=set(spy.payload['understandings'][0]['evidence_ids']+spy.payload['understandings'][0]['counter_evidence_ids'])
    body['question']='这次不会怎么考虑？'
    assert client.post(path,headers=oh,json=body).status_code==200
    assert len(retrieved)==2


def test_cancelled_prefetch_stops_before_new_database_preparation(app,client,session,monkeypatch):
    import app.api.twin as twin
    from app.api.twin import SourceChanged
    o,r,oh,rh,ep,other,source,extra,root,spy=setup(app,client,session)
    picker=provider(monkeypatch,source);seen=[];original=twin.generate_answer
    def stop():raise SourceChanged('Call ended')
    def invoke(*a,**kw):return original(*a,**kw,prepare_only=True,cancel_check=stop)
    old=picker.retrieve
    def counted(q):seen.append(q);return old(q)
    picker.retrieve=counted
    monkeypatch.setattr(twin,'generate_answer',invoke)
    response=client.post(f'/api/v1/subjects/{o.subject_id}/twin/answers',headers=oh,json={
        'question':'这次怎么考虑？','mode':'persona','retrieval_mode':'local','cloud_consent_id':cloud(client,o.subject_id,oh)})
    assert response.status_code==409
    assert seen==[] and spy.payload is None
