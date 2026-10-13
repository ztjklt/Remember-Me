"""Alibaba adapters. Only Backend holds credentials or sees provider voice IDs."""
import json
import subprocess
import tempfile
import wave
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
import aiohttp
import httpx
from .errors import AppError


class RealtimeUnavailable(AppError):
    code = 'REALTIME_UNAVAILABLE'
    http_status = 503


def validate_sample(data: bytes) -> float:
    if not data or len(data) > 8 * 1024 * 1024:
        raise RealtimeUnavailable('声音样本为空或超过 8 MB。')
    with tempfile.TemporaryDirectory(prefix='rm-voice-') as directory:
        source = Path(directory) / 'input.m4a'
        target = Path(directory) / 'sample.wav'
        source.write_bytes(data)
        try:
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                            '-t', '16', '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(target)],
                           capture_output=True, check=True, timeout=20)
            with wave.open(str(target)) as audio:
                duration = audio.getnframes() / audio.getframerate()
                pcm = audio.readframes(audio.getnframes())
            import array
            values = array.array('h', pcm)
            energy = (sum(v*v for v in values) / max(1, len(values))) ** .5
            if not 5 <= duration <= 15 or energy < 180:
                raise ValueError()
            return duration
        except (OSError, subprocess.SubprocessError, wave.Error, ValueError) as exc:
            raise RealtimeUnavailable('请录制 5–15 秒清晰、只有本人说话的声音。') from exc


def task_message(action, task_id, payload):
    return {'header': {'action': action, 'task_id': task_id, 'streaming': 'duplex'},
            'payload': payload}


class AlibabaVoice:
    def __init__(self, settings):
        self.settings = settings

    def configured(self):
        s = self.settings
        base = urlsplit(s.cosyvoice_base_url)
        websocket = urlsplit(s.realtime_inference_url)
        allowed = lambda host: host in {'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com'} or (host or '').endswith('.maas.aliyuncs.com')
        return bool(s.cosyvoice_api_key.get_secret_value() and base.scheme == 'https' and
                    allowed(base.hostname) and websocket.scheme == 'wss' and allowed(websocket.hostname))

    def operation(self, action, *, timeout_seconds=45, **fields):
        if not self.configured():
            raise RealtimeUnavailable('云端个人声音服务尚未配置。')
        try:
            with httpx.Client(timeout=timeout_seconds, follow_redirects=False, trust_env=False) as client:
                response = client.post(self.settings.cosyvoice_base_url.rstrip('/') + '/services/audio/tts/customization',
                    headers={'Authorization': 'Bearer ' + self.settings.cosyvoice_api_key.get_secret_value()},
                    json={'model': 'voice-enrollment', 'input': {'action': action, **fields}})
                response.raise_for_status()
                return response.json()['output']
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise RealtimeUnavailable('百炼声音请求失败，请检查服务权限或稍后重试。') from exc

    async def speech(self, text, voice_id, model):
        task_id = uuid4().hex
        headers = {'Authorization': 'Bearer ' + self.settings.cosyvoice_api_key.get_secret_value()}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90), trust_env=False) as client:
            async with client.ws_connect(self.settings.realtime_inference_url, headers=headers,
                                         max_msg_size=2*1024*1024, heartbeat=10) as ws:
                await ws.send_json(task_message('run-task', task_id, {
                    'task_group': 'audio', 'task': 'tts', 'function': 'SpeechSynthesizer',
                    'model': model, 'parameters': {'text_type': 'PlainText', 'voice': voice_id,
                    'format': 'pcm', 'sample_rate': 24000}, 'input': {}}))
                started = False
                async for message in ws:
                    if message.type == aiohttp.WSMsgType.BINARY:
                        if not started: raise RealtimeUnavailable('声音服务返回顺序错误。')
                        yield message.data
                    elif message.type == aiohttp.WSMsgType.TEXT:
                        event = json.loads(message.data)
                        if event.get('header', {}).get('task_id') != task_id:
                            raise RealtimeUnavailable('声音任务编号不匹配。')
                        kind = event['header'].get('event')
                        if kind == 'task-started':
                            started = True
                            await ws.send_json(task_message('continue-task', task_id, {'input': {'text': text}}))
                            await ws.send_json(task_message('finish-task', task_id, {'input': {}}))
                        elif kind == 'task-finished': return
                        elif kind == 'task-failed': raise RealtimeUnavailable('个人声音生成失败，请稍后重试。')
                    else:
                        raise RealtimeUnavailable('个人声音连接中断。')
                raise RealtimeUnavailable('个人声音连接未正常完成。')


def enrollment_prefix(identifier):
    # Stable, per-operation namespace for reconciling an unknown create outcome.
    import hashlib
    alphabet='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    value=int.from_bytes(hashlib.sha256(identifier.encode()).digest()[:16],'big')
    result=''
    for _ in range(10): value,remainder=divmod(value,62);result+=alphabet[remainder]
    return result
