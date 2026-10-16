from app.contracts import AICoreInput, AICoreOutput
from app.recording_highlights import validated_highlights, annotate_output
from app.providers.ollama import grounded_result
from app.providers.base import ModelRequest
from app.providers.weixin import WeixinProvider
from app.errors import AIOutputInvalid
import pytest


def payload():
    return AICoreInput(episode_id='ep_test', subject_id='s', transcript='我喜欢散步。我不会借钱投资。',
        existing_model_version='v1', subject_context={'recording_highlights': {
            'version':'recording-highlights-v1', 'spans':[{'span_start':6, 'span_end':14, 'excerpt':'我不会借钱投资。'}]}})


def request():
    return ModelRequest(payload=payload(), system_prompt='', response_schema={}, model='test',
        model_version='test', prompt_version='test', schema_version='integration-contract-v0.2')


def test_priority_reorders_memories_without_changing_confidence_or_full_text():
    req=request()
    raw=grounded_result({'memories':[
        dict(quote='我喜欢散步。',statement='喜欢散步',domain='PREFERENCES',memory_type='PREFERENCE',confidence=0.9),
        dict(quote='我不会借钱投资。',statement='不会借钱投资',domain='DECISION_PATTERNS',memory_type='VALUE',confidence=0.7)]},req)
    out=annotate_output(req.payload,AICoreOutput.model_validate(raw))
    assert out.memory_items[0].content=='不会借钱投资'
    assert out.memory_items[0].confidence==0.7
    assert out.memory_items[0].metadata['recording_priority']['weight']==2.0
    assert len(out.memory_items)==2 and req.payload.transcript=='我喜欢散步。我不会借钱投资。'


def test_invalid_spans_cannot_gain_priority():
    p=payload(); p.subject_context['recording_highlights']['spans'][0]['excerpt']='我会借钱投资。'
    assert validated_highlights(p)==[]


def test_live_provider_receives_focus_with_all_sources_and_no_confidence_boost():
    provider=WeixinProvider(api_key='test')
    captured=[]
    provider.complete=lambda instruction,data: (captured.append((instruction,data)) or ({'memories':[]},'test'))
    provider.generate(request())
    instruction,data=captured[0]
    assert len(data['sources'])==2
    assert data['sources'][0]['priority_weight']==1.0
    assert data['sources'][1]['priority_weight']==2.0
    assert '不得因重点而提高 confidence' in instruction
    provider.close()


def test_nonverbatim_anchor_gets_one_bounded_repair_with_same_sources():
    provider=WeixinProvider(api_key='test')
    calls=[]
    def complete(instruction,data,**kw):
        calls.append((instruction,data,kw))
        anchors={'negation':['我不会去借钱投资']} if len(calls)==1 else {}
        return {'memories':[dict(source_ids=['s2'], statement='不会借钱投资',domain='DECISION_PATTERNS',
            memory_type='VALUE',confidence=0.7,anchors=anchors)]},'test'
    provider.complete=complete
    result=provider.generate(request())
    assert len(calls)==2 and calls[0][1]==calls[1][1]
    assert '逐字' in calls[1][0] and 0<calls[1][2]['timeout_seconds']<=45
    assert result['memory_items'][0]['confidence']==0.7
    assert result['memory_items'][0]['metadata']['semantic_anchors']['negation']==[]
    assert result['evidence'][0]['excerpt']=='我不会借钱投资。'
    provider.close()


def test_repeated_bad_anchor_still_fails_without_infinite_retry():
    provider=WeixinProvider(api_key='test'); calls=[]
    def complete(*args,**kw):
        calls.append(1)
        return {'memories':[dict(source_ids=['s2'],statement='不会借钱投资',domain='DECISION_PATTERNS',
            memory_type='VALUE',confidence=0.7,anchors={'negation':['改写的原文']})]},'test'
    provider.complete=complete
    with pytest.raises(AIOutputInvalid,match='Semantic anchor'):
        provider.generate(request())
    assert len(calls)==2
    provider.close()
