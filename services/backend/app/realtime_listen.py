"""Service-authenticated streaming ASR proxy, with live authorization checks."""
import asyncio
import json
from uuid import uuid4
import aiohttp
from fastapi import WebSocketDisconnect
from .errors import AppError
from .realtime_access import check_call
from .realtime_provider import task_message


async def proxy_listen(ws, call_id):
    from .api.realtime import worker_authorization
    app=ws.app
    def authorize():
        with app.state.database.session() as session:
            check_call(session,call_id,app.state.settings,app.state.realtime_provider)
    try:
        worker_authorization(ws)
        authorize()
    except AppError:
        await ws.close(code=1008);return
    await ws.accept()
    task_id=uuid4().hex
    tasks=[]
    try:
        headers={'Authorization':'Bearer '+app.state.settings.cosyvoice_api_key.get_secret_value()}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800),trust_env=False) as client:
            async with client.ws_connect(app.state.settings.realtime_inference_url,headers=headers,max_msg_size=128*1024,heartbeat=10) as upstream:
                await upstream.send_json(task_message('run-task',task_id,{'task_group':'audio','task':'asr','function':'recognition',
                    'model':app.state.settings.realtime_asr_model,'parameters':{'format':'pcm','sample_rate':16000,
                    'semantic_punctuation_enabled':False,'max_sentence_silence':600},'input':{}}))
                first=await asyncio.wait_for(upstream.receive_json(),15)
                if first.get('header',{}).get('event')!='task-started': raise RuntimeError('ASR unavailable')
                await ws.send_json({'type':'ready'})
                async def send_audio():
                    count=0
                    async for data in ws.iter_bytes():
                        if not data or len(data)>32000 or len(data)%2: raise ValueError('Invalid PCM frame')
                        count+=len(data)
                        if count>16000*2*1800: raise ValueError('Call audio limit')
                        authorize()
                        await upstream.send_bytes(data)
                async def receive_text():
                    async for packet in upstream:
                        if packet.type!=aiohttp.WSMsgType.TEXT: raise RuntimeError('ASR disconnected')
                        event=json.loads(packet.data)
                        if event.get('header',{}).get('task_id')!=task_id: raise ValueError('Task mismatch')
                        kind=event['header'].get('event')
                        if kind=='task-failed': raise RuntimeError('ASR failed')
                        if kind=='task-finished': return
                        if kind=='result-generated':
                            sentence=event.get('payload',{}).get('output',{}).get('sentence',{})
                            text=sentence.get('text','')
                            if sentence.get('heartbeat') or not text.strip(): continue
                            if len(text)>1000: raise ValueError('Question too long')
                            authorize()
                            await ws.send_json({'type':'final' if sentence.get('sentence_end') else 'interim',
                                                'text':text,'sentence_id':str(sentence.get('begin_time',0))})
                async def watchdog():
                    while True:
                        await asyncio.sleep(1)
                        authorize()
                tasks=[asyncio.create_task(f()) for f in [send_audio,receive_text,watchdog]]
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done: task.result()
    except (AppError,WebSocketDisconnect,RuntimeError,ValueError,aiohttp.ClientError,asyncio.TimeoutError):
        try: await ws.send_json({'type':'error','message':'实时识别连接中断或授权已变化，请结束后重试。'})
        except (RuntimeError,WebSocketDisconnect): pass
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        try: await ws.close()
        except RuntimeError: pass
