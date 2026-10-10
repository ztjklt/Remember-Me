"""Current portrait must not revive masked text from a still-active sibling."""
from sqlalchemy import select
import pytest
from app.models import MemoryItem, Evidence, Episode
from app.materials import effective_materials
from test_agent_workbench import setup_pair


@pytest.mark.parametrize('partial',[False,True])
def test_portrait_excludes_shared_excerpt_containing_superseded_fact(app,client,session,partial):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    quote=session.get(Evidence,old.evidence_ids[0]).excerpt
    old.review_state='superseded'
    ids=list(old.evidence_ids)
    if partial:
        episode=session.get(Episode,ep)
        start=len(episode.transcript)+1
        valid='我常在院子里照料花。'
        episode.transcript+='。'+valid
        session.add(Evidence(evidence_id='valid-sibling-source',episode_id=ep,source_type='SUBJECT',
            source_ref='test:valid-sibling',excerpt=valid,span_start=start,span_end=start+len(valid)))
        ids.append('valid-sibling-source')
    sibling=MemoryItem(memory_item_id='sibling',episode_id=ep,ordinal=10,memory_type='PREFERENCE',
        content='另一条仍标为有效的摘要',source_type='SUBJECT',evidence_ids=ids,
        review_state='active',confidence=1,model_version='test',prompt_version='test',schema_version='test')
    session.add(sibling);session.commit()
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    portrait=client.get(root+'/portrait',headers=oh)
    assert portrait.status_code==200,portrait.text
    assert quote not in str(portrait.json()['views'])
    assert '另一条仍标为有效的摘要' not in str(portrait.json()['views'])
    materials=effective_materials(session,owner.subject_id,{ep})
    assert all(m['memory_item_id']!='sibling' for m in materials)
    if partial: assert any(valid in e['excerpt'] for m in materials for e in m['evidence'])
    # Source history is still available to its owner.
    assert quote in client.get(root+'/stories',headers=oh).json()['items'][0]['transcript']
