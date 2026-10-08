from copy import deepcopy
import pytest
from app.causal import CausalLink, attach
from app.errors import EvidenceInvalid
from test_reflection import run


def link(quote='我现在喝茶更安心', relation='REPORTED_CAUSE'):
    return CausalLink.model_validate({'assertion_memory_index':0,'relation':relation,'quote':quote,
        'cause':{'memory_index':0,'quote':'喝茶'}, 'effect':{'memory_index':0,'quote':'更安心'}})


def test_causal_worker_requires_explicit_causality_not_association():
    output,_=run({'updates':[],'facets':[]})
    with pytest.raises(EvidenceInvalid):
        attach([link()],output,[])
    attach([link(relation='ASSOCIATED_WITH')],output,[])
    item=output.memory_items[0].metadata['temporal_causal'][0]
    assert item['relation']=='ASSOCIATED_WITH' and item['cause']['quote']=='喝茶'
    assert item['evidence_ids']==output.memory_items[0].evidence_ids


def test_historical_anchor_is_snapshot_linked_and_cannot_be_forged():
    output,_=run({'updates':[],'facets':[]})
    old={'memory_item_id':'old','content':'过去的饮品','evidence':[{'evidence_id':'ev-old','source_type':'SUBJECT','excerpt':'以前喝咖啡'}]}
    payload=link(relation='BEFORE').model_dump(); payload['cause']={'memory_item_id':'old','quote':'喝咖啡'}
    attach([CausalLink.model_validate(payload)],output,[old])
    assert output.memory_items[0].metadata['temporal_causal'][0]['cause']['content']=='过去的饮品'
    old['evidence'][0]['source_type']='THIRD_PARTY'
    with pytest.raises(EvidenceInvalid): attach([CausalLink.model_validate(payload)],output,[old])
    with pytest.raises(EvidenceInvalid): attach([CausalLink.model_validate(payload)],output,[])


def test_forged_time_and_assertion_quotes_fail_closed():
    output,_=run({'updates':[],'facets':[]})
    payload=link(relation='BEFORE').model_dump(); payload['cause']['time_text']='2020年'
    with pytest.raises(EvidenceInvalid): attach([CausalLink.model_validate(payload)],output,[])
    payload=link(relation='BEFORE').model_dump(); payload['quote']='我没说过的原因'
    with pytest.raises(EvidenceInvalid): attach([CausalLink.model_validate(payload)],output,[])


def test_reflection_attaches_causal_metadata_in_same_worker_call():
    output,provider=run({'updates':[],'facets':[],'causal_links':[link(relation='ASSOCIATED_WITH').model_dump()]})
    assert len(provider.calls)==1
    assert output.memory_items[0].metadata['temporal_causal'][0]['version']=='temporal-causal-v1'
