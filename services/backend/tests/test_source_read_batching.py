"""Query growth must follow archive batches, not one round trip per citation."""
import pytest
from sqlalchemy import event, select
from app.models import Evidence, MemoryItem
from app.materials import effective_materials
from app.twin_context import contextual_evidence
from test_integration_materials import setup_pair


@pytest.mark.parametrize('operation',['materials','context'])
def test_many_citations_use_bounded_reads_without_changing_provenance(app,client,session,operation):
    own,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    original=session.get(Evidence,memory.evidence_ids[0])
    refs=[];sources={}
    for n in range(30):
        id=f'batch-citation-{n}';refs.append(id)
        session.add(Evidence(evidence_id=id,episode_id=ep,source_type=original.source_type,
            source_ref=original.source_ref,excerpt=original.excerpt,
            span_start=original.span_start,span_end=original.span_end))
        sources[id]=dict(evidence_id=id,episode_id=ep,source_type=original.source_type,
            excerpt=original.excerpt,temporal_context='')
    memory.evidence_ids=refs;session.commit();session.expunge_all()
    queries=[]
    def record(conn,cursor,statement,*args):
        if statement.lstrip().upper().startswith('SELECT'):queries.append(statement)
    event.listen(session.bind,'before_cursor_execute',record)
    try:
        if operation=='materials':
            rows=effective_materials(session,own.subject_id,{ep})
            result={e['evidence_id']:e for c in rows for e in c['evidence']}
        else:result=contextual_evidence(session,sources)
    finally:event.remove(session.bind,'before_cursor_execute',record)
    assert set(refs)<=result.keys()
    assert all(result[id]['excerpt']==sources[id]['excerpt'] and result[id]['episode_id']==ep for id in refs)
    assert len(queries)<=8, len(queries)
