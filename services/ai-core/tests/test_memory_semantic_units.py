import pytest
from app.contracts import AICoreInput
from app.extractor import MemoryExtractor
from app.errors import AIOutputInvalid
from app.providers.weixin import WeixinProvider


def run(text, item):
    provider = WeixinProvider(api_key='test-only')
    provider.complete = lambda *args, **kwargs: ({'memories': [item]}, 'test-model')
    try:
        return MemoryExtractor(provider=provider,model='test',model_version='test').process(
            AICoreInput(episode_id='ep',subject_id='subject',transcript=text,existing_model_version='v1'))
    finally:
        provider.close()


def candidate(**extra):
    return dict(statement='讲述者给孩子买画笔时有例外，原因尚不确定。',domain='PREFERENCES',
        memory_type='PREFERENCE',confidence=.8,**extra)


def test_multiple_sources_keep_intervening_exception_and_exact_offsets():
    text='我平时省钱。给孩子买画笔不一样。可能想到女儿小时候，我也说不清。'
    item=candidate(source_ids=['s1','s3'],anchors={'uncertainty':['可能','说不清'],
        'conditions':['给孩子买画笔不一样']})
    result=run(text,item)
    memory=result.memory_items[0]
    assert len(memory.evidence_ids)==3
    assert ''.join(e.excerpt for e in result.evidence)==text
    assert memory.metadata['semantic_anchors']['uncertainty']==['可能','说不清']
    for e in result.evidence:
        assert text[e.span_start:e.span_end]==e.excerpt


def test_repeated_sentence_uses_selected_occurrence():
    result=run('我喜欢安静。以前不一样。我喜欢安静。',candidate(source_ids=['s3']))
    assert result.evidence[0].span_start==len('我喜欢安静。以前不一样。')


@pytest.mark.parametrize('extra',[
    {'source_ids':['s100']}, {'source_ids':['s1','s1']},
    {'source_ids':['s1'],'anchors':{'subject':['桂芳']}},
    {'source_ids':['s1'],'source_id':'s1'},
])
def test_unknown_duplicate_or_invented_anchor_rejected(extra):
    with pytest.raises(AIOutputInvalid):run('我喜欢安静。',candidate(**extra))
