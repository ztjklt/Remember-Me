"""Actual duplex ASR and preset streaming TTS. No file-request fallback."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


class RealtimeFailure(RuntimeError):
    def __init__(self, code: str, message: str = '语音连接暂时不可用。'):
        self.code = code
        super().__init__(message)


def realtime_url(base: str) -> str:
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query
            or parsed.fragment or parsed.port or not re.fullmatch(
                r'llm-[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com', parsed.netloc)
            or parsed.path.rstrip('/') not in {'', '/compatible-mode/v1'}):
        raise RealtimeFailure('ASR_CONFIG_INVALID')
    return f'wss://{parsed.netloc}/api-ws/v1/inference'


def asr_start(task_id: str, silence_ms: int) -> dict:
    if not 200 <= silence_ms <= 6000: raise ValueError('Invalid endpoint silence')
    return {'header': {'action': 'run-task', 'task_id': task_id, 'streaming': 'duplex'},
        'payload': {'task_group': 'audio', 'task': 'asr', 'function': 'recognition',
            'model': 'paraformer-realtime-v2', 'parameters': {'format': 'pcm', 'sample_rate': 16000,
                'language_hints': ['zh'], 'semantic_punctuation_enabled': False,
                'max_sentence_silence': silence_ms, 'disfluency_removal_enabled': False,
                'heartbeat': True}, 'input': {}}}


def parse_asr(data: dict) -> dict | None:
    event = data.get('header', {}).get('event')
    if event == 'task-failed':
        # Vendor descriptions may contain request data. Never echo them to clients.
        raise RealtimeFailure('ASR_TASK_FAILED', '实时识别未完成，请检查服务权限或稍后重试。')
    if event == 'task-started': return {'type': 'asr_ready'}
    if event == 'task-finished': return {'type': 'asr_finished'}
    if event != 'result-generated': return None
    sentence = data.get('payload', {}).get('output', {}).get('sentence', {})
    if sentence.get('heartbeat'): return None
    text = sentence.get('text', '')
    if not isinstance(text, str) or len(text) > 4000:
        raise RealtimeFailure('ASR_OUTPUT_INVALID')
    if not text.strip(): return None
    return {'type': 'transcript', 'text': text, 'final': sentence.get('sentence_end') is True,
            'begin_ms': sentence.get('begin_time'), 'end_ms': sentence.get('end_time')}


async def pcm_from_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Incremental SSE framing, independent of TCP/HTTP boundaries."""
    pending = b''
    count = 0
    async for chunk in chunks:
        pending += chunk
        if len(pending) > 2 * 1024 * 1024:
            raise RealtimeFailure('TTS_OUTPUT_INVALID')
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            line = line.rstrip(b'\r')
            if not line.startswith(b'data:'): continue
            data = line[5:].strip()
            if data == b'[DONE]':
                if not count: raise RealtimeFailure('TTS_EMPTY')
                return
            try:
                item = json.loads(data)
                if item.get('error'): raise RealtimeFailure('TTS_PROVIDER_FAILED')
                choices = item.get('choices', [])
                if not isinstance(choices, list): raise ValueError()
                for choice in choices:
                    encoded = (choice.get('delta', {}).get('audio') or {}).get('data')
                    if encoded is None: continue
                    pcm = base64.b64decode(encoded, validate=True)
                    if not pcm or len(pcm) % 2: raise ValueError()
                    count += len(pcm)
                    if count > 24_000 * 2 * 120: raise RealtimeFailure('TTS_OUTPUT_TOO_LONG')
                    yield pcm
            except (ValueError, TypeError, AttributeError, binascii.Error) as exc:
                raise RealtimeFailure('TTS_OUTPUT_INVALID') from exc
    raise RealtimeFailure('TTS_TRUNCATED', '声音传输中断，可重试播放。')


class ParaformerRealtime:
    def __init__(self, settings, silence_ms: int = 800):
        self.url = realtime_url(settings.paraformer_base_url)
        self.key = settings.paraformer_api_key.get_secret_value()
        self.silence_ms = silence_ms
        self.task_id = uuid4().hex
        self.socket = None
        if not self.key: raise RealtimeFailure('ASR_NOT_CONFIGURED')

    async def __aenter__(self):
        from websockets.asyncio.client import connect
        try:
            self.socket = await connect(self.url, additional_headers={'Authorization': 'Bearer '+self.key},
                open_timeout=15, close_timeout=2, max_size=256_000, max_queue=8, proxy=None)
            await self.socket.send(json.dumps(asr_start(self.task_id, self.silence_ms)))
            async with asyncio.timeout(15):
                event = parse_asr(json.loads(await self.socket.recv()))
                if not event or event['type'] != 'asr_ready':
                    raise RealtimeFailure('ASR_HANDSHAKE_FAILED')
            return self
        except BaseException:
            if self.socket is not None: await self.socket.close()
            raise

    async def send(self, pcm: bytes):
        if not pcm or len(pcm) % 2 or len(pcm) > 32_000:
            raise RealtimeFailure('AUDIO_INVALID')
        await self.socket.send(pcm)

    async def events(self):
        async for raw in self.socket:
            try: event = parse_asr(json.loads(raw))
            except (ValueError, TypeError, AttributeError) as exc:
                raise RealtimeFailure('ASR_OUTPUT_INVALID') from exc
            if event: yield event

    async def finish(self):
        await self.socket.send(json.dumps({'header': {'action': 'finish-task', 'task_id': self.task_id,
            'streaming': 'duplex'}, 'payload': {'input': {}}}))

    async def __aexit__(self, *exc):
        if self.socket: await self.socket.close()


class XiaomiRealtime:
    def __init__(self, settings):
        if settings.xiaomi_voice_base_url.rstrip('/') != 'https://api.xiaomimimo.com/v1':
            raise RealtimeFailure('TTS_CONFIG_INVALID')
        self.url = settings.xiaomi_voice_base_url.rstrip('/') + '/chat/completions'
        self.key = settings.xiaomi_voice_api_key.get_secret_value()
        if not self.key: raise RealtimeFailure('TTS_NOT_CONFIGURED')

    async def stream(self, text: str):
        if not text.strip() or len(text) > 1500: raise RealtimeFailure('TTS_TEXT_INVALID')
        payload = {'model': 'mimo-v2.5-tts', 'stream': True,
            'messages': [{'role': 'assistant', 'content': text}],
            'audio': {'format': 'pcm16', 'voice': '白桦'}}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=15), trust_env=False,
                                         follow_redirects=False) as client:
                async with client.stream('POST', self.url, headers={'Authorization': 'Bearer '+self.key},
                                         json=payload) as response:
                    if response.status_code != 200:
                        code = 'TTS_AUTH_FAILED' if response.status_code in {401,403} else 'TTS_HTTP_FAILED'
                        raise RealtimeFailure(code, f'语音合成连接失败（HTTP {response.status_code}）。')
                    async with asyncio.timeout(90):
                        async for pcm in pcm_from_sse(response.aiter_bytes()): yield pcm
        except httpx.HTTPError as exc:
            raise RealtimeFailure('TTS_NETWORK_FAILED') from exc
