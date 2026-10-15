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
