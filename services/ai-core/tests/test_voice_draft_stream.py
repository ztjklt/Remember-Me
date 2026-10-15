import asyncio
import json
from types import SimpleNamespace
import pytest
from app.errors import AIOutputInvalid
from app.quoted_twin import QuotedTwin
from test_grounded_twin import data


def test_rejected_semantic_review_only_emits_internal_draft_not_final():
    from app.voice_stream import voice_response
    class Chat:
        def complete(self,system,payload):
            if 'selection' not in payload:
                return {'points':[{'known':True,'source_ids':['s1']}]},'test'
            return {'reasoning':'Incorrect attribution','valid':False,
                'failure_codes':['attribution'],'replacement':None},'test'
    async def run():
        payload=data();payload.voice_response=True
        response=voice_response(lambda:QuotedTwin(Chat()).answer(payload))
        events=[json.loads(line) async for line in response.body_iterator]
        assert [e['type'] for e in events]==['draft','error']
        assert '老周' in events[0]['text']
        assert events[-1]['code']=='AI_SCHEMA_INVALID'
        assert not any(e['type']=='final' for e in events)
    asyncio.run(run())


def test_draft_is_available_while_semantic_review_is_still_pending():
    from app.voice_stream import voice_response
    from threading import Event
    review=Event()
    class Chat:
        def complete(self,system,payload):
            if 'selection' not in payload:
                return {'points':[{'known':True,'source_ids':['s1']}]},'test'
            assert review.wait(2)
            return {'reasoning':'Supported','valid':True,'failure_codes':[], 'replacement':None},'test'
    async def run():
        payload=data();payload.voice_response=True
        response=voice_response(lambda:QuotedTwin(Chat()).answer(payload))
        iterator=response.body_iterator
        first=json.loads(await anext(iterator))
        assert first['type']=='draft' and not review.is_set()
        review.set()
        remaining=[json.loads(line) async for line in iterator]
        assert [e['type'] for e in remaining]==['final']
        assert remaining[0]['result']['answer']==first['text']
    asyncio.run(run())
