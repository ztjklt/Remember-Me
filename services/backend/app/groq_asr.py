"""Groq hosted Whisper; no local ASR, script hints or provider fallback.

Official multipart speech endpoint. The product job owns the retry budget;
authorization is checked after the serial wait and immediately before sending.
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .audio_transport import compact_audio
from .errors import SttFailed, SttTimeout, SttUnavailable
from .relay_asr import SerialGate
from .stt import Transcript

ENDPOINT = 'https://api.groq.com/openai/v1/audio/transcriptions'
PROTOCOL_VERSION = 'groq-zh-multipart-v1'


def configured(settings):
    return bool(settings.groq_api_key.get_secret_value().strip())


def cloud_policy(settings):
    payload = [ENDPOINT, settings.groq_asr_model, PROTOCOL_VERSION, 'mp3_48k', 'zh']
    return 'cloud-asr-v1:' + hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:32]


class GroqSttProvider:
    backend = 'groq'

    def __init__(self, settings, *, gate=None):
        self.settings = settings
        self.policy_id = cloud_policy(settings)
        self.directory = Path(settings.groq_asr_state_dir)
        self.gate = gate or SerialGate(self.directory)

    def transcribe(self, audio, content_type):
        return self.transcribe_authorized(audio, content_type, lambda: None)

    def transcribe_authorized(self, audio, content_type, authorize):
        if not configured(self.settings):
            raise SttFailed('Groq 云端转写密钥未配置；不会切换服务或运行本地模型。')
        if not audio or len(audio) > self.settings.max_upload_bytes:
            raise SttFailed('待转写原音为空或超出大小限制。')
        with self.gate.slot():
            authorize()
            wire = compact_audio(audio)
            authorize()
            return self._request(audio, wire)

    def _request(self, audio, wire):
        started = time.monotonic()
        record = {'at': datetime.now(timezone.utc).isoformat(), 'endpoint': ENDPOINT,
            'request_model': self.settings.groq_asr_model, 'response_model': None,
            'prompt_version': PROTOCOL_VERSION, 'prompt_supplied': False,
            'audio_sha256': hashlib.sha256(audio).hexdigest(), 'audio_bytes': len(audio),
            'wire_audio_sha256': hashlib.sha256(wire).hexdigest(), 'wire_audio_bytes': len(wire),
            'audio_transport': 'mp3_48k', 'wire_format': 'multipart', 'language': 'zh',
            'http_status': None, 'finish_reason': 'unreported', 'usage': None,
            'validation': 'failed', 'audio_alignment_verified': False}
        try:
            try:
                response = httpx.post(ENDPOINT,
                    headers={'Authorization': 'Bearer ' + self.settings.groq_api_key.get_secret_value()},
                    files={'file': ('recording.mp3', wire, 'audio/mpeg')},
                    data={'model': self.settings.groq_asr_model, 'language': 'zh',
                          'response_format': 'verbose_json', 'temperature': '0'},
                    timeout=httpx.Timeout(self.settings.stt_timeout_seconds),
                    follow_redirects=False, trust_env=True)
            except httpx.TimeoutException as error:
                raise SttTimeout('Groq 云端转写超时，原音保留。') from error
            except httpx.HTTPError as error:
                raise SttUnavailable('Groq 云端转写连接失败，原音保留。') from error
            record['http_status'] = response.status_code
            if response.status_code == 429:
                self.gate.defer(305)
                raise SttUnavailable('Groq 云端转写限流，进入有界冷却与任务重试。')
            if response.status_code in {500, 502, 503, 504}:
                raise SttUnavailable(f'Groq 暂时不可用（HTTP {response.status_code}）。')
            if response.status_code != 200:
                raise SttFailed(f'Groq 请求被拒绝（HTTP {response.status_code}），请检查配置或额度。')
            try:
                body = response.json()
                text = body['text']
            except (ValueError, KeyError, TypeError) as error:
                raise SttFailed('Groq 转写返回结构不符合约定。') from error
            if not isinstance(text, str) or not text.strip() or len(text) > 30000:
                raise SttFailed('Groq 转写为空或超出文本范围，未作为成功结果保存。')
            if isinstance(body.get('duration'), (float, int)):
                record['reported_duration_seconds'] = body['duration']
            record['reported_segments'] = len(body['segments']) if isinstance(body.get('segments'), list) else None
            # Provider does not promise a model/usage field in verbose_json.
            # Requested route is provenance, not proof of underlying weights.
            record['validation'] = 'transcript_received_unreviewed'
            return Transcript(text.strip(), self.backend, 'groq/' + self.settings.groq_asr_model, record)
        except (SttFailed, SttTimeout, SttUnavailable) as error:
            record['error_code'] = error.code
            raise
        finally:
            record['elapsed_seconds'] = round(time.monotonic() - started, 3)
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / 'calls.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(record, ensure_ascii=False) + '\n')
