from sqlalchemy import event, select

from app.models import MemoryItem
from app.retrieval import retrieve
from app.seed import seed_development_data
from test_twin_voice import _record, TinyEncoder


def test_warm_retrieval_batches_evidence_and_vectors_without_changing_ranking(app,client,session):
    own=seed_development_data(session,subject_name='Batch fixture',actor_name='Owner')
    headers={'Authorization':'Bearer '+own.actor_token}
    episode=_record(client,app,own.subject_id,own.consent_id,headers)
    original=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==episode))
    values={c.name:getattr(original,c.name) for c in original.__table__.columns}
    for index in range(20):
        session.add(MemoryItem(**dict(values,memory_item_id=f'batch-{index:02}')))
    session.commit()
    first=retrieve(session,own.subject_id,'喜欢散步',TinyEncoder(),limit=30,episode_ids={episode})
    session.commit();session.expunge_all()
    reads=[]
    def observe(conn,cursor,statement,params,context,many):
        text=statement.lower()
        if text.lstrip().startswith('select') and ('from memory_embeddings' in text or 'from evidence' in text):
            reads.append(text)
    event.listen(session.bind,'before_cursor_execute',observe)
    try:
        second=retrieve(session,own.subject_id,'喜欢散步',TinyEncoder(),limit=30,episode_ids={episode})
    finally:event.remove(session.bind,'before_cursor_execute',observe)
    assert first==second
    assert len(second)>=20
    assert len(reads)<=5, f'{len(reads)} evidence/vector SELECTs for one query'
