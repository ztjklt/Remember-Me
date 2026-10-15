import asyncio
import json
import pytest
from app.quoted_twin import QuotedTwin
from app.voice_stream import voice_response
from test_grounded_twin import data


def collect(function, **kw):
    async def run():
        return [json.loads(line) async for line in voice_response(function, **kw).body_iterator]
    return asyncio.run(run())


class Chat:
    def __init__(self, source='s1'):
        self.calls=0; self.source=source
    def complete(self, system, payload):
        self.calls+=1
        if 'selection' in payload:
            return dict(reasoning='Wrong attribution',valid=False,failure_codes=['attribution'],replacement=None),'test'
        return {'points':[{'known':True,'source_ids':[self.source]}]},'test'


def test_fast_skips_only_semantic_review_and_context_resets():
    payload=data();payload.voice_response=True
    chat=Chat()
    events=collect(lambda:QuotedTwin(chat).answer(payload), review_required=False)
    assert chat.calls==1
    assert events[-1]['type']=='final'
    assert events[-1]['semantic_review']=='skipped'
    assert events[-1]['result']['evidence_ids']==['e1']
    # Same provider/data in the ordinary path still invokes and honors review.
    events=collect(lambda:QuotedTwin(chat).answer(payload))
    assert events[-1]['type']=='error' and chat.calls==3


def test_fast_still_rejects_invented_sources():
    payload=data();payload.voice_response=True
    chat=Chat('not-a-source')
    events=collect(lambda:QuotedTwin(chat).answer(payload), review_required=False)
    assert events[-1]['type']=='error'
    assert not any(e['type'] in {'final','draft'} for e in events)
    assert chat.calls==2


def test_fast_context_cannot_disable_review_for_text_requests():
    events=collect(lambda:QuotedTwin(Chat()).answer(data()), review_required=False)
    assert events[-1]['type']=='error'


def test_persona_fast_keeps_conditional_sources_without_claiming_reviewed_coverage():
    from app.persona import PersonaInput, PersonaProvider
    from test_persona import payload, point, ScriptedChat
    data=PersonaInput.model_validate(dict(payload(),voice_response=True))
    chat=ScriptedChat({'points':[point()]})
    events=collect(lambda:PersonaProvider(chat).answer(data),review_required=False)
    result=events[-1]
    assert result['type']=='final' and result['semantic_review']=='skipped'
    assert len(chat.requests)==1
    assert result['result']['understanding_ids']==['u-real']
    assert result['result']['evidence_ids']==['e1','e2']
    assert result['result']['prompt_version']=='persona-conditional-fast-v8'
    assert 'coverage' not in result['result'] and 'omitted_points' not in result['result']
