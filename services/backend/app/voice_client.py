"""Loopback-only adapter for the Mac voice synthesis process."""

from urllib.parse import urlsplit

import httpx


class VoiceUnavailable(RuntimeError):
    pass


class VoiceSampleInvalid(RuntimeError):
    pass


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
