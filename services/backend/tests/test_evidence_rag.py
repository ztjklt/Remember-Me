"""Original-evidence retrieval invariants; fake vectors are test doubles only."""
import json
from sqlalchemy import select
from app.models import Episode, EvidenceChunkEmbedding
from test_agent_workbench import setup_pair
from test_twin_context import capture


def test_postgres_vector_operator_works_with_isolated_search_path():
    from sqlalchemy import bindparam, cast
    from sqlalchemy.dialects.postgresql import dialect
    from app.vector_type import PGVector
    distance = EvidenceChunkEmbedding.vector.op('OPERATOR(public.<=>)')(
        cast(bindparam('query_vector', [1., 0.], type_=PGVector()), PGVector()))
    sql = str(select(distance).compile(dialect=dialect()))
    assert 'OPERATOR(public.<=>)' in sql
    assert 'AS public.vector' in sql
    assert PGVector().bind_processor(dialect())([1., 0.]) == '[1.0, 0.0]'


class TopicEncoder:
    version = 'test-topic-v1'
    def __init__(self): self.calls = []
    def encode(self, texts):
        self.calls.extend(texts)
        return [[1.,0.,0.] if any(w in t for w in ['图书馆','阅读','借书','看书']) else
                [0.,1.,0.] if '金融' in t else [0.,0.,1.] for t in texts]


def clone_episode(session, ep, id, text):
    original = session.get(Episode, ep)
    values = {c.name:getattr(original,c.name) for c in Episode.__table__.columns}
    values.update(episode_id=id, idempotency_key=id, transcript=text)
    session.add(Episode(**values)); session.commit()


def test_large_library_retrieves_unextracted_fact_and_its_complete_context(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    session.get(Episode,ep).transcript+='。我去图书馆看书，因为那里安静。书名暂时没有决定。'
    session.commit()
    for n in range(30): clone_episode(session,ep,f'irrelevant-{n}', '金融报告里的销售额只是测试材料。'*70)
    app.state.embedding_encoder=TopicEncoder();seen=capture(app)
    response=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'我去哪里阅读，为什么？','cloud_consent_id':cloud})
    assert response.status_code==200,response.text
    snippets=[e['excerpt'] for c in seen for e in c['evidence']]
    assert any('图书馆' in s and '因为那里安静' in s for s in snippets)
    assert any('没有决定' in s for s in snippets)
    assert not any('金融报告' in s for s in snippets)
    assert sum(map(len,snippets))<24000
    assert all(e['episode_id']==ep for c in seen for e in c['evidence'])


def test_search_indexes_raw_gaps_and_reuses_vectors_without_reencoding_library(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    session.get(Episode,ep).transcript+='。我常去图书馆看书。';session.commit()
    encoder=TopicEncoder();app.state.embedding_encoder=encoder
    path=f'/api/v1/subjects/{owner.subject_id}/memory-search'
    first=client.get(path,headers=oh,params={'q':'去哪阅读？'})
    assert first.status_code==200,first.text
    assert any('图书馆' in e['excerpt'] for item in first.json()['items'] for e in item['evidence'])
    assert session.scalar(select(EvidenceChunkEmbedding).where(EvidenceChunkEmbedding.subject_id==owner.subject_id))
    encoder.calls.clear()
    assert client.get(path,headers=oh,params={'q':'去哪阅读？'}).status_code==200
    assert encoder.calls==['去哪阅读？']


def test_unrelated_query_returns_unknown_without_sending_unrelated_material_to_llm(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    app.state.embedding_encoder=TopicEncoder();seen=capture(app)
    r=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'金融收入是多少？','cloud_consent_id':cloud})
    assert r.status_code==200,r.text
    assert r.json()['response_type']=='UNKNOWN' and seen==[]


def test_reader_never_recalls_owner_private_recording(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    clone_episode(session,ep,'private-books','我把私人物品放在图书馆。')
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    grant=client.post(root+'/grants',headers=oh,json={'episode_id':ep,'reader_actor_id':reader.actor_id,
        'include_audio_confirmed':True,'cloud_processing_allowed':True}).json()
    app.state.embedding_encoder=TopicEncoder();seen=capture(app)
    r=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=rh,
        json={'question':'图书馆里放了什么？','cloud_consent_id':grant['grant_id']})
    assert r.status_code==200,r.text
    assert '私人物品' not in json.dumps(seen,ensure_ascii=False)
    session.expire_all()
    sources=list(session.scalars(select(EvidenceChunkEmbedding).where(EvidenceChunkEmbedding.subject_id==owner.subject_id)))
    from app.models import Evidence
    assert all(session.get(Evidence,r.evidence_id).episode_id==ep for r in sources)


def test_counter_evidence_expansion_preserves_the_other_recording_context(app,client,session):
    from app.materials import effective_materials
    from app.evidence_rag import prepare,publish_and_select
    from app.access import publication_lock,source_basis
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    session.get(Episode,ep).transcript+='。我去图书馆阅读。';session.commit()
    clone_episode(session,ep,'counter','那次赶时间。我没有去，先回家了。')
    candidates=effective_materials(session,owner.subject_id,{ep,'counter'},enforce_budget=False)
    support=next(e['evidence_id'] for c in candidates for e in c['evidence'] if '图书馆' in e['excerpt'])
    counter=next(e['evidence_id'] for c in candidates for e in c['evidence'] if '我没有去' in e['excerpt'])
    basis=source_basis(session,owner.subject_id);session.commit()
    plan=prepare(session,owner.subject_id,'去哪阅读？',candidates,TopicEncoder())
    publication_lock(session,owner.subject_id);assert basis==source_basis(session,owner.subject_id)
    result=publish_and_select(session,plan,candidates,related_groups=[{support,counter}])
    texts=[e['excerpt'] for c in result for e in c['evidence']]
    assert '那次赶时间。' in texts
    assert '我没有去，先回家了。' in texts
