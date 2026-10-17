import asyncio,json
import httpx
from test_weixin_deadline import bounded_chat,envelope


def test_slow_primary_can_still_win_and_negative_verdict_is_not_outvoted(monkeypatch):
    calls=[];closed=[]
    async def handle(request):
        n=len(calls)+1;calls.append(json.loads(request.content))
        try:
            await asyncio.sleep(.18 if n==1 else 1)
            body=envelope();body['choices'][0]['message']['content']=json.dumps({'valid':n!=1})
            return httpx.Response(200,json=body)
        finally:closed.append(n)
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=2,json_retry_after_seconds=.1,json_hedged=True):
            result,_=chat.complete('Keep all checks',{'evidence':'unchanged'})
        assert result=={'valid':False} and len(calls)==2 and calls[0]==calls[1]
        assert set(closed)=={1,2}
    finally:chat.close()


def test_ordinary_review_uses_only_one_request_with_hedge_enabled(monkeypatch):
    calls=[]
    async def handle(request):calls.append(request);return httpx.Response(200,json=envelope())
    chat=bounded_chat(monkeypatch,handle)
    try:
        with chat.transport_scope(timeout_seconds=1,json_retry_after_seconds=.2,json_hedged=True):
            assert chat.complete('review',{})[0]=={'valid':True}
        assert len(calls)==1
    finally:chat.close()
