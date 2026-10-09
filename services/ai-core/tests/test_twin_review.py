import pytest
from app.providers.weixin import WeixinTwinProvider
from app.twin import TwinInput
from app.errors import AIOutputInvalid


@pytest.mark.parametrize('accepted',[True,False])
def test_semantic_review_is_separate_and_failure_is_not_unknown(accepted):
    model=WeixinTwinProvider(api_key='test-only',verify_answers=True)
    calls=[]
    def complete(system,payload):
        calls.append(payload)
        if len(calls)==1:return dict(answer='讲述者以前住甲城，现在住乙城。',response_type='SIMULATION',evidence_ids=['s1'],confidence=.8),'Deepseek-v4-flash'
        assert payload['answer']=='讲述者以前住甲城，现在住乙城。'
        assert payload['cited_sources'][0]['excerpt']=='以前住甲城，后来搬到乙城。'
        return dict(supported=accepted,contradiction_free=accepted,answers_question=True,unknown_supported=True),'Deepseek-v4-flash'
    model.complete=complete
    data=TwinInput(question='以前和现在住哪里？',candidates=[dict(memory_item_id='m',statement='搬家',evidence=[dict(evidence_id='ev1',excerpt='以前住甲城，后来搬到乙城。',source_type='SUBJECT')])])
    if accepted:assert model.answer(data).response_type=='SIMULATION'
    else:
        with pytest.raises(AIOutputInvalid,match='evidence review'):model.answer(data)
    assert len(calls)==2
    model.close()


def test_invalid_review_booleans_fail_closed():
    model=WeixinTwinProvider(api_key='test-only',verify_answers=True)
    calls=[]
    def complete(system,payload):
        calls.append(payload)
        if len(calls)==1:return dict(answer='现有记录还不足以确定。',response_type='UNKNOWN',evidence_ids=[],confidence=0),'Deepseek-v4-flash'
        return dict(supported='true',contradiction_free=True,answers_question=True,unknown_supported=True),'Deepseek-v4-flash'
    model.complete=complete
    data=TwinInput(question='在哪？',candidates=[dict(memory_item_id='m',statement='甲城',evidence=[dict(evidence_id='ev1',excerpt='住在甲城。',source_type='SUBJECT')])])
    with pytest.raises(AIOutputInvalid):model.answer(data)
    model.close()


def test_global_unknown_cannot_precede_a_simulated_explanation():
    model=WeixinTwinProvider(api_key='test-only',verify_answers=True)
    calls=[]
    def complete(system,payload):
        calls.append(payload)
        if len(calls)>1:
            return dict(supported=True,contradiction_free=True,answers_question=True,unknown_supported=True),'Deepseek-v4-flash'
        return dict(answer='现有记录还不足以确定。讲述者这样做是因为家人等他。',response_type='SIMULATION',evidence_ids=['s1'],confidence=.8),'Deepseek-v4-flash'
    model.complete=complete
    data=TwinInput(question='为什么？',candidates=[dict(memory_item_id='m',statement='原因未讲',evidence=[dict(evidence_id='ev1',excerpt='原因还没有讲。',source_type='SUBJECT')])])
    with pytest.raises(AIOutputInvalid,match='global unknown'):
        model.answer(data)
    assert len(calls)==1
    model.close()
