"""Opt-in A/B/C model-stage experiment; never imports into the running service.

Only run against frozen backend-authorized fictional packets. No APK output,
production answer publication, live grants, or biometric enrollment here.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import logging
import os
import time
import wave
from threading import Event
from pathlib import Path
from types import SimpleNamespace

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr
from app.config import Settings
from app.providers.weixin import WeixinChat, BASE_URL, MODEL
from app.quoted_twin import QuotedTwin, SYSTEM, VERSION, SourceSelection, quote_packet, render_ids
from app.twin import TwinInput
from app.voice_stream import draft_observer
from app.cancellation import cancelled_request, check_cancelled
from ablation_core import SSE, CompletePoints, StreamFailure, fast_answer


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request_body(payload):
    packet, _ = quote_packet(payload)
    packet['response_schema'] = SourceSelection.model_json_schema()
    stable = ('recordings', 'confirmed_understanding', 'understandings', 'examples', 'contributions', 'response_schema')
    ordered = {k: packet[k] for k in stable if k in packet}
    ordered.update({k: v for k, v in packet.items() if k not in ordered})
    return {'model': MODEL, 'messages': [{'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': json.dumps(ordered, ensure_ascii=False, separators=(',', ':'))}],
        'response_format': {'type': 'json_object'}}


async def streamed_selection(key, payload, on_point, record, timeout):
    body = request_body(payload)
    body['stream'] = True
    start = time.perf_counter()
    sse = SSE()
    points = CompletePoints(record)
    model = None
    record['stream_stage'] = 'connect'
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient(trust_env=False, timeout=timeout, follow_redirects=False) as client:
            async with client.stream('POST', BASE_URL + '/chat/completions', json=body,
                    headers={'Authorization': 'Bearer ' + key}) as response:
                record['http_status'] = response.status_code
                record['stream_stage'] = 'headers'
                if response.status_code != 200: raise StreamFailure('stream HTTP rejected')
                record['content_type'] = response.headers.get('content-type', '')
                if 'text/event-stream' not in record['content_type']: raise StreamFailure('not SSE')
                record['stream_stage'] = 'sse'
                async for chunk in response.aiter_bytes():
                    for event in sse.feed(chunk):
                        if event.get('model'):
                            if model and model != event['model']: raise StreamFailure('model changed')
                            model = event['model']
                            if not isinstance(model, str) or len(model) > 128: raise StreamFailure('model invalid')
                            record['response_model'] = model
                        if isinstance(event.get('usage'), dict): record['usage'] = event['usage']
                        for choice in event.get('choices', []):
                            if choice.get('index', 0) != 0: raise StreamFailure('unexpected choice')
                            delta = choice.get('delta', {})
                            if delta.get('refusal') or delta.get('tool_calls'): raise StreamFailure('unsupported output')
                            text = delta.get('content')
                            if text:
                                record.setdefault('first_token_ms', round((time.perf_counter()-start)*1000, 3))
                                for point in points.feed(text):
                                    if not model: raise StreamFailure('missing model identity')
                                    record['stream_stage'] = 'point_validation'
                                    validated, _ = render_ids({'points': [point]}, payload, model)
                                    record.setdefault('first_point_ms', round((time.perf_counter()-start)*1000, 3))
                                    await on_point(validated)
                                    record['stream_stage'] = 'sse'
                sse.finish()
    if not model: raise StreamFailure('missing model identity')
    record['stream_stage'] = 'final_validation'
    record['selection_json'] = points.finish()
    record['stream_done_ms'] = round((time.perf_counter()-start)*1000, 3)
    result = render_ids(record['selection_json'], payload, model)[0]
    record['stream_stage'] = 'complete'
    return result


async def stream_with_retry(key, payload, on_point, record):
    """Same two transport attempts until output is released; never replay audio."""
    released = False
    start = time.perf_counter()
    attempts = []
    summary_keys = set()
    async def emit(result):
        nonlocal released
        released = True
        await on_point(result)
    for index in range(2):
        attempt = {'begin_ms': round((time.perf_counter()-start)*1000, 3)}
        attempts.append(attempt)
        try:
            result = await streamed_selection(key, payload, emit, attempt, 8)
            return result
        except Exception as exc:
            attempt['error'] = type(exc).__name__
            transient = isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.TransportError)) or attempt.get('http_status') in (408, 500, 502, 503, 504)
            if released or index or not transient: raise
            await asyncio.sleep(.3)
        finally:
            for field in summary_keys: record.pop(field, None)
            record.update(attempt)
            summary_keys = set(attempt)
            record['stream_attempts'] = attempts
            for timing in ('first_token_ms', 'first_point_ms', 'stream_done_ms'):
                if timing in attempt: record[timing] = attempt['begin_ms'] + attempt[timing]


async def run_once(mode, payload, chat, stream_fn, tts, prepared_module, output):
    started = time.perf_counter()
    elapsed = lambda: round((time.perf_counter()-started)*1000, 3)
    record = {'mode': mode, 'status': 'failed', 'review': 'blocking' if mode == 'A' else 'not_run',
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    pcm = bytearray()
    prepared = prepared_module.PreparedSpeech(tts)
    audio_task = None
    early_text = None
    calls = []
    loop = asyncio.get_running_loop()
    futures = []
    cancelled = Event()

    async def audio(text, use_prepared=False):
        record['tts_text'] = text
        iterator = prepared.stream(text) if use_prepared else tts(text)
        async for chunk in iterator:
            record.setdefault('first_pcm_ms', elapsed())
            pcm.extend(chunk)
        if not pcm: raise StreamFailure('empty TTS')
        record['audio_done_ms'] = elapsed()

    async def first_point(result):
        nonlocal audio_task, early_text
        if audio_task is None:
            early_text = prepared_module.sentences(result.answer)[0]
            record['first_point_released_ms'] = elapsed()
            audio_task = asyncio.create_task(audio(early_text))

    class RecordedChat:
        def complete(self, system, packet):
            begin = elapsed()
            try:
                raw, model = chat.complete(system, packet)
                calls.append({'begin_ms': begin, 'end_ms': elapsed(), 'model': model,
                              'prompt_sha256': hashlib.sha256(system.encode()).hexdigest(), 'raw': raw})
                return raw, model
            except Exception as exc:
                calls.append({'begin_ms': begin, 'end_ms': elapsed(), 'error': type(exc).__name__})
                raise

    def blocking():
        async def prepare_if_active(text):
            if not cancelled.is_set(): await prepared.prepare(text)
        def draft(event):
            check_cancelled()
            record['draft_ms'] = elapsed()
            future = asyncio.run_coroutine_threadsafe(prepare_if_active(event['text']), loop)
            futures.append(future)
            future.result(timeout=2)
        cancel_token = cancelled_request.set(cancelled)
        token = draft_observer.set(draft if mode == 'A' else None)
        try:
            with chat.transport_scope(timeout_seconds=8):
                return QuotedTwin(RecordedChat()).answer(payload) if mode == 'A' else fast_answer(RecordedChat(), payload)
        finally:
            draft_observer.reset(token)
            cancelled_request.reset(cancel_token)

    try:
        result = await stream_fn(payload, first_point, record) if mode == 'C' else await asyncio.to_thread(blocking)
        record['validated_text_ms'] = elapsed()
        record['answer'] = result.model_dump(mode='json')
        first = prepared_module.sentences(result.answer)[0]
        # The existing renderer adds quotation punctuation when a later point
        # changes ORIGINAL into SIMULATION. Only that wrapper may differ.
        spoken = lambda s: s.strip().removeprefix('“').removesuffix('”')
        if early_text is not None and spoken(early_text) != spoken(first):
            raise StreamFailure('first sentence changed')
        if audio_task is None: audio_task = asyncio.create_task(audio(first, mode == 'A'))
        await audio_task
        record['status'] = 'ok'
    except asyncio.CancelledError:
        record['status'] = 'cancelled'
        raise
    except Exception as exc:
        record['status'] = 'partial_failed' if pcm else 'failed'
        record['error'] = type(exc).__name__
        record['error_code'] = getattr(exc, 'code', None)
    finally:
        cancelled.set()
        for future in futures:
            if not future.done(): future.cancel()
        if audio_task is not None and not audio_task.done():
            audio_task.cancel()
        if audio_task is not None: await asyncio.gather(audio_task, return_exceptions=True)
        await prepared.close()
        record['calls'] = calls
        record['total_ms'] = elapsed()
        record['pcm_bytes'] = len(pcm)
        if pcm and output:
            with wave.open(str(output), 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(pcm)
            output.chmod(0o600)
    return record


async def main(args):
    os.umask(0o077)
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=args.ai_env)
    key = settings.weixin_api_key.get_secret_value()
    env = {k.lower().removeprefix('remember_'): v for k, v in dotenv_values(args.api_env).items()}
    provider = load(Path(args.backend)/'app'/'realtime_providers.py', 'experiment_realtime')
    prepared = load(Path(args.backend)/'app'/'prepared_speech.py', 'experiment_prepared')
    tts = provider.XiaomiRealtime(SimpleNamespace(xiaomi_voice_base_url=env.get('xiaomi_voice_base_url', 'https://api.xiaomimimo.com/v1'),
        xiaomi_voice_api_key=SecretStr(env['xiaomi_voice_api_key'])))
    chat = WeixinChat(api_key=key)
    logging.getLogger('remember_me.ai_core').addHandler(logging.FileHandler(directory/'calls.jsonl'))
    rows = json.loads(Path(args.packets).read_text(encoding='utf-8'))
    async def stream(payload, on_point, record):
        return await stream_with_retry(key, payload, on_point, record)
    try:
        for repeat in range(args.repeats):
            for index, item in enumerate(rows):
                modes = 'ABC'
                offset = (repeat + index + args.order_offset) % 3
                for mode in modes[offset:] + modes[:offset]:
                    name = f'{repeat+1}-{item["id"]}-{mode}'
                    path = directory/(name+'.json')
                    if path.exists(): raise RuntimeError('Use a fresh output directory; preserve earlier trials')
                    payload = TwinInput.model_validate(item['payload'])
                    record = await run_once(mode, payload, chat, stream, tts.stream, prepared, directory/(name+'.wav'))
                    record.update(case=item['id'], repeat=repeat+1, prompt_version=VERSION,
                        endpoint=BASE_URL+'/chat/completions', requested_model=MODEL,
                        packet_sha256=hashlib.sha256(json.dumps(item['payload'], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                        scope='model_and_first_sentence_tts_only')
                    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps({k: record.get(k) for k in ('case','repeat','mode','status','first_pcm_ms','validated_text_ms','first_token_ms','first_point_ms','error')}, ensure_ascii=False), flush=True)
                    if record.get('http_status') in (401, 403, 429) or record.get('error') in ('ProviderAuthenticationFailed', 'ProviderRateLimited'):
                        raise RuntimeError('Provider blocked; no automatic repeated calls')
                    await asyncio.sleep(args.pause_seconds)
    finally: chat.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--ai-env', required=True); p.add_argument('--api-env', required=True)
    p.add_argument('--backend', required=True); p.add_argument('--packets', required=True)
    p.add_argument('--output', required=True); p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--order-offset', type=int, default=0)
    p.add_argument('--pause-seconds', type=float, default=3)
    asyncio.run(main(p.parse_args()))
