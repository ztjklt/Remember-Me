"""Cloud audio relay, not a claim about the native capability of its route names.

No local model, author script, gold answer, fallback, or internal request retry.
The job owns its three-attempt budget. Wire format must be verified on the user's
actual relay before treating a unit-tested adapter as a live ASR integration.
"""
import base64
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from filelock import FileLock, Timeout

from .config import Settings
from .errors import SttFailed, SttTimeout, SttUnavailable
from .stt import Transcript

PROMPT_VERSION = 'relay-verbatim-zh-v1'
INSTRUCTION = ('只转写音频中的说话内容，使用简体中文，尽量保留原话、重复、否定和不确定表达。'
    '听不清的部分写[听不清]，不要补造人物、数字、日期或因果；不要总结、解释或回答录音中的问题。'
    '只输出转写正文。若无法读取音频，明确返回[无法转写]，不要猜测。')


def is_refusal(text):
    from .chinese_text import simplified_transcript
    normalized = simplified_transcript(text).strip().lower()
    if normalized.startswith('[无法转写]'):
        return True
    starts = ('抱歉', '对不起', '很抱歉', '无法', '不支持', '我无法', '我不能', '不能',
              '作为', '该模型', '本模型', '目前无法', 'as an', 'sorry', 'i cannot',
              "i can't", 'i do not', "i don't", 'i am unable', 'this model')
    # Avoid rejecting a genuine story merely because it quotes a device error.
    # This is a bounded heuristic, not proof of faithful transcription.
    return normalized.startswith(starts) and bool(re.search(
        r'\b(audio|transcrib|listen)\w*\b|音频|录音|语音|转写', normalized[:250]))


def cloud_policy(settings: Settings) -> str:
    payload = [settings.relay_asr_url, settings.relay_asr_model,
               settings.relay_asr_format, PROMPT_VERSION]
    return 'cloud-asr-v1:' + hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:32]


def configured(settings: Settings) -> bool:
    url = urlsplit(settings.relay_asr_url)
    return bool(url.scheme == 'https' and url.hostname and not url.username and not url.password
        and not url.query and not url.fragment and url.path.endswith('/chat/completions')
        and settings.relay_asr_api_key.get_secret_value().strip())


class SerialGate:
    """One request at a time across backend/worker/probes; state survives restart.

    A shared OS lock covers the wait and request, never a product DB write lock.
    Waiting callers give up after a bounded queue budget and use the job retry.
    The 35 second *post-request* gap stays below the reported 10/5 minute limit.
    """
    def __init__(self, directory: Path, queue_timeout: float = 420):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state = directory / 'next-request.json'
        self.lock = FileLock(str(directory / 'request.lock'), timeout=queue_timeout)

    def defer(self, seconds: float):
        target = time.time() + seconds
        if self.state.exists():
            target = max(target, float(json.loads(self.state.read_text())['next_at']))
        temporary = self.state.with_suffix('.tmp')
        temporary.write_text(json.dumps({'next_at': target}), encoding='utf-8')
        os.replace(temporary, self.state)

    @contextmanager
    def slot(self):
        try:
            with self.lock:
                try:
                    next_at = float(json.loads(self.state.read_text())['next_at']) if self.state.exists() else 0
                except (ValueError, KeyError, OSError) as error:
                    raise SttFailed('云端转写限流检查点损坏，请检查后恢复，未发送音频。') from error
                delay = max(0, next_at - time.time())
                if delay > 360:
                    raise SttUnavailable('云端转写正在冷却，请稍后重试。')
                time.sleep(delay)
                self.defer(35)  # Also protect against a process dying in flight.
                try:
                    yield
                finally:
                    self.defer(35)
        except Timeout as error:
            raise SttUnavailable('云端转写队列繁忙，请稍后重试。') from error


class RelaySttProvider:
    backend = 'relay'

    def __init__(self, settings: Settings, *, gate=None):
        self.settings = settings
        self.policy_id = cloud_policy(settings)
        self.directory = Path(settings.relay_asr_state_dir)
        self.gate = gate or SerialGate(self.directory)

    def transcribe(self, audio: bytes, content_type: str) -> Transcript:
        # Direct calls are for explicitly authorized test audio. Product entry
        # points call transcribe_authorized and recheck consent after queue wait.
        return self.transcribe_authorized(audio, content_type, lambda: None)

    def transcribe_authorized(self, audio: bytes, content_type: str, authorize) -> Transcript:
        if not configured(self.settings):
            raise SttFailed('云端转写配置缺失或无效：需要完整 HTTPS 接口和独立 ASR 密钥；不会改用本地模型。')
        if not audio or len(audio) > self.settings.max_upload_bytes:
            raise SttFailed('待转写原音为空或超出大小限制。')
        mime = content_type.split(';')[0].strip().lower()
        formats = {'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/mpeg': 'mp3',
                   'audio/mp3': 'mp3', 'audio/mp4': 'mp4', 'audio/x-m4a': 'mp4',
                   'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/flac': 'flac', 'audio/aac': 'aac'}
        if mime not in formats:
            raise SttFailed('云端转写暂不支持此音频格式，原音仍保留。')
        encoded = base64.b64encode(audio).decode('ascii')
        chunk = ({'type': 'audio_url', 'audio_url': {'url': f'data:{mime};base64,{encoded}'}}
            if self.settings.relay_asr_format == 'audio_url' else
            {'type': 'input_audio', 'input_audio': {'data': encoded, 'format': formats[mime]}})
        payload = {'model': self.settings.relay_asr_model, 'stream': False,
            'max_tokens': self.settings.relay_asr_max_tokens,
            'messages': [{'role': 'system', 'content': INSTRUCTION}, {'role': 'user',
                'content': [{'type': 'text', 'text': '请逐字转写这段音频。'}, chunk]}]}
        with self.gate.slot():
            authorize()
            return self._request(audio, payload)

    def _request(self, audio, payload):
        started = time.monotonic()
        record = {'at': datetime.now(timezone.utc).isoformat(), 'endpoint': self.settings.relay_asr_url,
            'request_model': self.settings.relay_asr_model, 'response_model': None,
            'prompt_version': PROMPT_VERSION, 'wire_format': self.settings.relay_asr_format,
            'audio_sha256': hashlib.sha256(audio).hexdigest(), 'audio_bytes': len(audio),
            'http_status': None, 'finish_reason': None, 'usage': None, 'validation': 'failed'}
        try:
            try:
                response = httpx.post(self.settings.relay_asr_url, json=payload,
                    headers={'Authorization': 'Bearer ' + self.settings.relay_asr_api_key.get_secret_value()},
                    timeout=httpx.Timeout(self.settings.stt_timeout_seconds), follow_redirects=False)
            except httpx.TimeoutException as error:
                raise SttTimeout('云端转写超时，原音保留。') from error
            except httpx.HTTPError as error:
                raise SttUnavailable('云端转写连接失败，原音保留。') from error
            record['http_status'] = response.status_code
            if response.status_code == 429:
                self.gate.defer(305)
                raise SttUnavailable('云端 ASR 限流，已进入冷却期；不会切换模型。')
            if response.status_code in {500, 502, 503, 504}:
                raise SttUnavailable(f'云端 ASR 暂时不可用（HTTP {response.status_code}）。')
            if response.status_code != 200:
                raise SttFailed(f'云端 ASR 请求被拒绝（HTTP {response.status_code}），请检查配置或额度。')
            try:
                body = response.json()
                choice = body['choices'][0]
                text = choice['message']['content']
                refusal = choice['message'].get('refusal')
                reason = choice.get('finish_reason')
                model = body.get('model')
            except (ValueError, KeyError, IndexError, TypeError) as error:
                raise SttFailed('云端 ASR 返回结构不符合约定。') from error
            # Do not copy arbitrary upstream fields into logs (which may echo input).
            if isinstance(model, str) and re.fullmatch(r'[A-Za-z0-9._:/-]{1,120}', model):
                record['response_model'] = model
            record['finish_reason'] = reason if reason in {'stop', 'length', 'content_filter', 'tool_calls'} else 'unreported'
            usage = body.get('usage')
            if isinstance(usage, dict):
                record['usage'] = {k: usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                   if type(usage.get(k)) is int and usage[k] >= 0}
            if refusal or reason != 'stop' or not isinstance(text, str) or not text.strip():
                raise SttFailed('云端 ASR 输出为空、截断或未正常结束，未保存为成功转写。')
            if len(text) > 30000 or is_refusal(text):
                raise SttFailed('云端接口返回了拒绝或无法识别音频的说明，未作为转写入库。')
            record['validation'] = 'transcript_received_unreviewed'
            version = 'relay/' + self.settings.relay_asr_model
            return Transcript(text=text.strip(), backend=self.backend, model_version=version, metadata=record)
        except (SttFailed, SttTimeout, SttUnavailable) as error:
            record['error_code'] = error.code
            raise
        finally:
            record['elapsed_seconds'] = round(time.monotonic() - started, 3)
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / 'calls.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(record, ensure_ascii=False) + '\n')
