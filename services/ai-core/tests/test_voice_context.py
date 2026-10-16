import asyncio
from threading import Event
import pytest
from app.cancellation import cancelled_request,cancellable
from app.errors import ProviderUnavailable
from app.twin import TwinInput
from app.grounded_twin import source_packet


def test_played_history_is_not_added_to_source_aliases():
    payload=TwinInput(question='后来呢？',candidates=[],voice_response=True,
        dialogue_context=[dict(question='那次呢？',heard_answer='不应变成历史事实。',interrupted=True)])
    packet,aliases=source_packet(payload)
    assert aliases=={} and packet['recordings']==[]
    assert packet['conversation_only_not_evidence'][0]['interrupted']
    assert '不应变成历史事实' not in str(packet['confirmed_understanding'])


def test_voice_selection_and_review_share_unresolved_reference_policy():
    from app.quoted_twin import QuotedTwin
    from test_grounded_twin import data
    payload=TwinInput.model_validate(dict(data().model_dump(),voice_response=True,
        question='你第一次参加这种活动是哪一年？',
        dialogue_context=[dict(question='你喜欢喝什么茶？',heard_answer='淡一点。',interrupted=False)]))
    class Chat:
        calls=0
        def complete(self,system,packet):
            self.calls+=1
            assert packet['question_context_policy']=={
                'history_field':'conversation_only_not_evidence',
                'unresolved_referent_is_unknown':True,
                'retrieved_source_must_not_define_question_referent':True,
                'explicit_history_reference_may_resolve_question':True}
            assert packet['conversation_only_not_evidence'][0]['question']=='你喜欢喝什么茶？'
            if 'selection' not in packet:
                return {'points':[{'known':False,'source_ids':[]}]},'actual'
            return {'reasoning':'Activity is unspecified; a retrieved event is not its referent.',
                    'valid':True,'failure_codes':[],'replacement':None},'actual'
    chat=Chat()
    assert QuotedTwin(chat).answer(payload).response_type=='UNKNOWN'
    assert chat.calls==2  # Unknown still undergoes semantic review.


def test_cancel_closes_active_transport_without_waiting_for_full_response():
    async def run():
        event=Event(); token=cancelled_request.set(event);closed=[]
        async def transport():
            try: await asyncio.sleep(10)
            finally: closed.append(True)
        task=asyncio.create_task(cancellable(transport()))
        await asyncio.sleep(.01);event.set()
        with pytest.raises(ProviderUnavailable): await asyncio.wait_for(task,.5)
        assert closed==[True]
        cancelled_request.reset(token)
    asyncio.run(run())
