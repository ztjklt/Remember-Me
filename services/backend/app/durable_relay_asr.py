"""Persist synchronous relay results; uncertain acknowledgements never replay audio."""
import hashlib
import json

from .relay_asr import RelaySttProvider
from .stt import Transcript
from .errors import SttFailed, SttUnavailable


class DurableRelaySttProvider(RelaySttProvider):
    def __init__(self, settings, checkpoint_store, *, gate=None):
        super().__init__(settings, gate=gate)
        self.checkpoints = checkpoint_store

    def transcribe_authorized(self, audio, content_type, authorize):
        authorize()
        identity = hashlib.sha256(self.policy_id.encode() + b'\0' + audio).hexdigest()
        key = 'asr-checkpoints/relay-' + identity + '.json'
        try:
            state_bytes = self.checkpoints.get(key)
        except FileNotFoundError:
            state = None
        except Exception as error:
            raise SttUnavailable('云端转写检查点不可读，未发送音频。') from error
        else:
            try:
                if len(state_bytes) > 512 * 1024:
                    raise ValueError('Oversized checkpoint')
                state = json.loads(state_bytes)
                if not isinstance(state, dict): raise ValueError('Invalid checkpoint')
            except (ValueError, TypeError, UnicodeError) as error:
                raise SttFailed('云端转写检查点无效，未重新发送音频。') from error
        if state is not None:
            if state.get('state') != 'complete':
                raise SttFailed('上次转写请求的结果不确定，需要核查；未重新发送原音。')
            result = state.get('transcript', {})
            if (not isinstance(result, dict) or set(result) != {'text', 'backend', 'model_version', 'metadata'}
                    or not isinstance(result['text'], str) or not result['text'].strip()
                    or len(result['text']) > 30000 or result['backend'] != self.backend
                    or not isinstance(result['model_version'], str)
                    or not isinstance(result['metadata'], dict)):
                raise SttFailed('云端转写结果检查点无效，未发送音频。')
            authorize()
            return Transcript(**result)
        return super().transcribe_authorized(audio, content_type, authorize)

    def _request(self, audio, payload, wire_audio, authorize=None):
        key = 'asr-checkpoints/relay-' + hashlib.sha256(
            self.policy_id.encode() + b'\0' + audio).hexdigest() + '.json'
        try:
            self.checkpoints.put(key, b'{"state":"submitting"}', 'application/json')
        except Exception as error:
            raise SttUnavailable('无法保存转写提交检查点，未发送音频。') from error
        try:
            if authorize is not None: authorize()
        except Exception:
            self.checkpoints.delete(key)
            raise
        self.last_http_status = None
        try:
            result = super()._request(audio, payload, wire_audio, authorize)
        except Exception:
            # These responses explicitly refused the request. A timeout/5xx/invalid
            # success body is ambiguous and leaves the submitting marker intact.
            if self.last_http_status in {400, 401, 403, 404, 413, 415, 422, 429}:
                self.checkpoints.delete(key)
            raise
        serialized = {'state': 'complete', 'transcript': {'text': result.text,
            'backend': result.backend, 'model_version': result.model_version,
            'metadata': result.metadata}}
        try:
            self.checkpoints.put(key, json.dumps(serialized, ensure_ascii=False).encode(), 'application/json')
        except Exception as error:
            raise SttFailed('转写响应未能持久保存，需要核查；不会重新提交原音。') from error
        return result
