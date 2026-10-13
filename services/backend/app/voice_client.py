"""Mac local voice and explicitly configured fictional Xiaomi voice adapters."""

from urllib.parse import urlsplit

import httpx
import base64
import binascii
import io
from pathlib import Path
import wave


class VoiceUnavailable(RuntimeError):
    pass


class VoiceSampleInvalid(RuntimeError):
    pass


def _validate_wav(data: bytes, max_bytes: int) -> None:
    if not data or len(data)>max_bytes:
        raise ValueError('Audio size invalid')
    with wave.open(io.BytesIO(data),'rb') as wav:
        if (not 1<=wav.getnchannels()<=2 or not 8000<=wav.getframerate()<=96000
                or wav.getnframes()<=0 or wav.getsampwidth() not in {1,2,3,4}):
            raise ValueError('Audio format invalid')
        expected=wav.getnframes()*wav.getnchannels()*wav.getsampwidth()
        if expected>max_bytes or len(wav.readframes(wav.getnframes()))!=expected:
            raise ValueError('Audio truncated')


def load_synthetic_reference(settings, subject_id: str) -> bytes:
    """The operator binds this reference to one fictional Subject, never a client."""
    if (settings.voice_synthetic_backend!='xiaomi' or not settings.a01_voice_subject_id
            or subject_id!=settings.a01_voice_subject_id or not settings.a01_voice_reference_path):
        raise VoiceUnavailable('合成声音未配置。')
    try:
        with Path(settings.a01_voice_reference_path).open('rb') as stream:
            data=stream.read(8*1024*1024+1)
        _validate_wav(data,8*1024*1024)
        return data
    except (OSError,ValueError,EOFError,wave.Error) as exc:
        raise VoiceUnavailable('服务器合成声音参考不可用。') from exc


class XiaomiSyntheticVoiceClient:
    """One bounded request, no automatic retries or provider fallback."""
    def __init__(self, settings, *, transport=None):
        parsed=urlsplit(settings.xiaomi_voice_base_url)
        if (parsed.scheme!='https' or parsed.hostname!='api.xiaomimimo.com'
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.port not in {None,443} or parsed.path.rstrip('/')!='/v1'):
            raise ValueError('Xiaomi voice endpoint must be the configured official HTTPS API')
        self.endpoint=settings.xiaomi_voice_base_url.rstrip('/')+'/chat/completions'
        self.model=settings.xiaomi_voice_model
        self._key=settings.xiaomi_voice_api_key.get_secret_value()
        self.timeout=min(max(settings.voice_timeout_seconds,1),300)
        self.transport=transport

    def synthesize(self, text: str, sample: bytes, transcript: str) -> tuple[bytes,str]:
        if not self._key or not text.strip() or len(text)>12000:
            raise VoiceUnavailable('合成声音配置或已保存回答不可用。')
        try:
            _validate_wav(sample,8*1024*1024)
            body={'model':self.model,'messages':[
                {'role':'user','content':'虚构人物的合成声音。平实温和，自然说话，完整逐字朗读，不省略；句间自然停顿。'},
                {'role':'assistant','content':text}],
                'audio':{'format':'wav','voice':'data:audio/wav;base64,'+base64.b64encode(sample).decode()}}
            with httpx.Client(timeout=self.timeout,trust_env=False,follow_redirects=False,
                              transport=self.transport) as client:
                with client.stream('POST',self.endpoint,json=body,
                        headers={'Authorization':'Bearer '+self._key}) as response:
                    response.raise_for_status()
                    chunks=[];size=0
                    for chunk in response.iter_bytes():
                        size+=len(chunk)
                        if size>24*1024*1024:raise ValueError('Audio response too large')
                        chunks.append(chunk)
            import json
            result=json.loads(b''.join(chunks))
            choice=result['choices'][0]
            model=result['model']
            if (choice.get('finish_reason') not in {None,'stop'} or not isinstance(model,str)
                    or not model.strip() or len(model)>128):
                raise ValueError('Model metadata or completion invalid')
            data=base64.b64decode(choice['message']['audio']['data'],validate=True)
            _validate_wav(data,16*1024*1024)
            return data,model
        except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError,EOFError,wave.Error,binascii.Error):
            # Neither exception bodies nor response text are safe public details.
            raise VoiceUnavailable('合成声音生成失败，请稍后重试。') from None


def build_synthetic_voice_client(settings):
    if settings.voice_synthetic_backend!='xiaomi' or not settings.xiaomi_voice_api_key.get_secret_value():
        return None
    return XiaomiSyntheticVoiceClient(settings)


class VoiceClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Voice service must be local loopback HTTP")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def validate(self, sample: bytes) -> dict:
        try:
            response = httpx.post(self.base_url + "/validate", content=sample,
                                  timeout=45, trust_env=False, follow_redirects=False)
            if response.status_code == 422:
                raise VoiceSampleInvalid("声音样本需要 5–15 秒、清晰且只有自然说话声，请重新录制。")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VoiceUnavailable("本机声音样本检查失败，请检查录音和声音服务。") from exc

    def synthesize(self, text: str, sample: bytes, transcript: str) -> tuple[bytes, str]:
        try:
            response = httpx.post(self.base_url + "/synthesize",
                                  data={"text": text, "reference_text": transcript},
                                  files={"sample": ("sample.m4a", sample, "audio/mp4")},
                                  timeout=self.timeout, trust_env=False, follow_redirects=False)
            response.raise_for_status()
            if response.headers.get("content-type", "").split(";")[0] != "audio/wav":
                raise VoiceUnavailable("声音模型没有返回音频。")
            return response.content, response.headers.get("X-Model-Version", "qwen3-tts-base")
        except httpx.HTTPError as exc:
            raise VoiceUnavailable("本机声音生成失败，请稍后重试。") from exc
