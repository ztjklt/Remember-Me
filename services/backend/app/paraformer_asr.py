"""Bailian Paraformer V2 file ASR, private temporary upload and resumable polling.

Only raw audio is exported. The job owns retries; a lost submit acknowledgement
requires investigation rather than silently creating a second billable task.
"""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote

import httpx
from filelock import FileLock, Timeout

from .errors import AppError, SttFailed, SttTimeout, SttUnavailable
from .stt import Transcript

MODEL = 'paraformer-v2'
PROTOCOL_VERSION = 'bailian-private-file-zh-v1'


def _client(timeout):
    return httpx.Client(timeout=timeout, follow_redirects=False)


def _base(settings):
    value = settings.paraformer_base_url.rstrip('/')
    u = urlsplit(value)
    if (u.scheme != 'https' or u.username or u.password or u.port or u.path
            or u.query or u.fragment or not re.fullmatch(
                r'llm-[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com', u.hostname or '')):
        raise SttFailed('百炼转写地址必须是北京工作空间 HTTPS 主机，不含 compatible-mode 路径。')
    return value


def configured(settings):
    try:
        _base(settings)
        return bool(settings.paraformer_api_key.get_secret_value().strip())
    except (ValueError, SttFailed):
        return False


def cloud_policy(settings):
    payload = [settings.paraformer_base_url.rstrip('/'), MODEL, PROTOCOL_VERSION,
               'private-temporary-oss-48h', 'zh', 'raw-audio']
    return 'cloud-asr-v1:' + hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:32]


def _oss_url(value):
    u = urlsplit(value)
    if (u.scheme != 'https' or u.username or u.password or u.port or u.fragment
            or not re.fullmatch(r'[a-z0-9-]+\.oss-cn-beijing\.aliyuncs\.com', u.hostname or '')):
        raise SttFailed('百炼返回了不受支持的文件地址，未向该地址发送数据。')
    return value


def _save(path, body):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def _same_file(value, state):
    if value == state['file_url']:
        return True
    # OssResourceResolve returns the upload object's signed HTTPS URL rather
    # than the submitted oss:// handle. Match the saved host AND exact key;
    # signatures are neither copied to checkpoints nor logged.
    actual = urlsplit(_oss_url(value))
    return (actual.hostname == state.get('upload_hostname')
            and unquote(actual.path).lstrip('/') == state['file_url'][6:])


class ParaformerSttProvider:
    backend = 'paraformer'

    def __init__(self, settings):
        self.settings = settings
        self.policy_id = cloud_policy(settings)
        self.directory = Path(settings.paraformer_state_dir)

    def transcribe(self, audio, content_type):
        return self.transcribe_authorized(audio, content_type, lambda: None)

    def transcribe_authorized(self, audio, content_type, authorize):
        if not configured(self.settings):
            raise SttFailed('百炼转写配置未完成；不会使用本地模型或替换供应商。')
        if not audio or len(audio) > self.settings.max_upload_bytes:
            raise SttFailed('待转写原音为空或超出大小限制。')
        base = _base(self.settings)
        digest = hashlib.sha256(audio).hexdigest()
        checkpoint_id = hashlib.sha256((self.policy_id + digest).encode()).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (checkpoint_id + '.json')
        record = {'at': datetime.now(timezone.utc).isoformat(), 'endpoint': base,
            'request_model': MODEL, 'response_model': None, 'prompt_version': PROTOCOL_VERSION,
            'prompt_supplied': False, 'audio_sha256': digest, 'audio_bytes': len(audio),
            'audio_transport': 'private-temporary-oss', 'temporary_retention_hours': 48,
            'http_status': None, 'usage': None, 'validation': 'failed',
            'audio_alignment_verified': False}
        started = time.monotonic()
        try:
            with FileLock(str(path) + '.lock', timeout=1), _client(self.settings.stt_timeout_seconds) as client:
                authorize()
                state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
                headers = {'Authorization': 'Bearer ' + self.settings.paraformer_api_key.get_secret_value()}

                def request(method, url, *, decode=True, submitting=False, **kwargs):
                    authorize()
                    try:
                        with client.stream(method, url, **kwargs) as response:
                            record['http_status'] = response.status_code
                            data = bytearray()
                            for chunk in response.iter_bytes():
                                data.extend(chunk)
                                if len(data) > 2 * 1024 * 1024:
                                    raise SttFailed('百炼返回内容超过大小限制。')
                            if response.status_code != 200:
                                status = response.status_code
                                if submitting:
                                    state['submission'] = 'rejected' if 400 <= status < 500 and status != 429 else 'unknown'
                                    _save(path, state)
                                if status == 429 or status in {500, 502, 503, 504}:
                                    raise SttUnavailable(f'百炼暂不可用（HTTP {status}），原音保留。')
                                raise SttFailed(f'百炼请求被拒绝（HTTP {status}），请检查授权或配置。')
                    except (httpx.TimeoutException, httpx.HTTPError) as exc:
                        if submitting:
                            raise SttFailed('百炼提交结果不确定，已保留检查点；请核查任务，避免重复提交。') from None
                        if isinstance(exc, httpx.TimeoutException):
                            raise SttTimeout('百炼转写请求超时，原音和任务检查点保留。') from None
                        raise SttUnavailable('百炼转写连接失败，原音和任务检查点保留。') from None
                    return json.loads(data) if decode else None

                if not state.get('task_id'):
                    if state.get('submission'):
                        raise SttFailed('此前百炼提交未获得可恢复任务编号，请核查检查点后再处理，未重复上传。')
                    policy = request('GET', base + '/api/v1/uploads', headers=headers,
                                     params={'action':'getPolicy', 'model':MODEL})['data']
                    host = _oss_url(policy['upload_host'])
                    if policy['x_oss_object_acl'] != 'private' or str(policy['x_oss_forbid_overwrite']).lower() != 'true':
                        raise SttFailed('百炼临时上传策略未保证私有且禁止覆盖，未外发原音。')
                    extension = {'audio/mp4':'.m4a', 'audio/x-m4a':'.m4a', 'audio/mpeg':'.mp3',
                                 'audio/wav':'.wav', 'audio/x-wav':'.wav', 'audio/webm':'.webm',
                                 'audio/ogg':'.ogg', 'audio/flac':'.flac'}.get(content_type.split(';')[0])
                    if extension is None:
                        raise SttFailed('此录音格式尚未接入百炼转写，原音保留。')
                    key = policy['upload_dir'].rstrip('/') + '/' + uuid.uuid4().hex + extension
                    fields = {'OSSAccessKeyId':policy['oss_access_key_id'], 'Signature':policy['signature'],
                        'policy':policy['policy'], 'x-oss-object-acl':'private', 'x-oss-forbid-overwrite':'true',
                        'key':key, 'success_action_status':'200'}
                    request('POST', host, decode=False, data=fields,
                            files={'file':('recording'+extension, audio, content_type)})
                    state = {'file_url':'oss://' + key, 'upload_hostname':urlsplit(host).hostname,
                             'submission':'submitting', 'created_at':time.time()}
                    authorize()
                    _save(path, state)
                    body = request('POST', base + '/api/v1/services/audio/asr/transcription', submitting=True,
                        headers={**headers, 'X-DashScope-Async':'enable', 'X-DashScope-OssResourceResolve':'enable'},
                        json={'model':MODEL, 'input':{'file_urls':[state['file_url']]}, 'parameters':{
                            'channel_id':[0], 'language_hints':['zh'], 'disfluency_removal_enabled':False}})
                    task_id = body['output']['task_id']
                    if not isinstance(task_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,128}', task_id):
                        raise SttFailed('百炼未返回有效任务编号，未重复提交。')
                    state['task_id'] = task_id; state['submission'] = 'accepted'
                    _save(path, state)
                record['task_id'] = state['task_id']
                if time.time() - state['created_at'] > 23 * 3600:
                    raise SttFailed('百炼任务结果已接近过期，请人工核查后重新处理；原音仍在。')
                deadline = time.monotonic() + self.settings.paraformer_poll_timeout_seconds
                while True:
                    body = request('GET', base + '/api/v1/tasks/' + state['task_id'], headers=headers)
                    output = body['output']; status = output['task_status']
                    if output.get('task_id') != state['task_id']:
                        raise SttFailed('百炼返回的任务编号不一致。')
                    if status == 'SUCCEEDED': break
                    if status not in {'PENDING', 'RUNNING'}:
                        no_speech_code = 'SUCCESS_WITH_NO_VALID_FRAGMENT'
                        results = output.get('results', [])
                        if (output.get('code') == no_speech_code or
                                isinstance(results, list) and any(
                                    isinstance(item, dict) and item.get('code') == no_speech_code
                                    for item in results)):
                            # Keep only a known code, never upstream messages or signed URLs.
                            record['provider_error_code'] = no_speech_code
                            raise SttFailed('音频已上传并保存在服务器；百炼未检测到有效语音，原音保留。'
                                            '请先试听原音；若能清楚听见讲话，请联系管理员核查。'
                                            '不要反复上传同一段录音。')
                        raise SttFailed('百炼转写任务未成功，原音保留。')
                    if time.monotonic() >= deadline:
                        raise SttTimeout('百炼任务仍在处理，将从原任务检查点重试。')
                    time.sleep(self.settings.paraformer_poll_interval_seconds)
                results = output['results']
                if (len(results) != 1 or results[0]['subtask_status'] != 'SUCCEEDED'
                        or not _same_file(results[0]['file_url'], state)):
                    raise SttFailed('百炼文件子任务失败或来源不一致，未保存转写。')
                result = request('GET', _oss_url(results[0]['transcription_url']))
                if not _same_file(result['file_url'], state):
                    raise SttFailed('百炼转写结果来源不一致。')
                channels = [t for t in result['transcripts'] if t['channel_id'] == 0]
                if len(channels) != 1:
                    raise SttFailed('百炼转写缺少唯一的目标声道。')
                text = channels[0]['text']
                if not isinstance(text, str) or not text.strip() or len(text) > 30000:
                    raise SttFailed('百炼转写为空或超出文本范围，未作为成功结果保存。')
                authorize()
                record['usage'] = body.get('usage')
                record['validation'] = 'transcript_received_unreviewed'
                return Transcript(text.strip(), self.backend, 'bailian/' + MODEL, record)
        except Timeout:
            record['error_code'] = 'STT_UNAVAILABLE'
            raise SttUnavailable('同一音频的百炼任务正在处理，稍后重试。') from None
        except (ValueError, KeyError, TypeError, IndexError):
            record['error_code'] = 'STT_FAILED'
            raise SttFailed('百炼返回结构或本地检查点不符合约定，未保存为成功。') from None
        except AppError as error:
            record['error_code'] = error.code
            raise
        finally:
            record['elapsed_seconds'] = round(time.monotonic() - started, 3)
            with (self.directory / 'calls.jsonl').open('a', encoding='utf-8') as output:
                output.write(json.dumps(record, ensure_ascii=False) + '\n')
