"""DashScope synchronous ASR adapter; recordings and credentials stay server-side."""

import base64

import httpx

from .errors import SttFailed, SttTimeout, SttUnavailable
from .stt import Transcript

FORMATS = {
    "audio/mp4": "mp4", "audio/m4a": "m4a", "audio/x-m4a": "m4a",
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3",
    "audio/aac": "aac", "audio/flac": "flac", "audio/x-flac": "flac",
    "audio/ogg": "ogg", "audio/opus": "opus", "audio/webm": "webm",
    "audio/amr": "amr",
}


class DashScopeSttProvider:
    backend = "dashscope"

    def __init__(self, *, base_url, path, model, api_key, timeout_seconds=60.0):
        if not model.strip() or not api_key.strip():
            raise ValueError("DashScope ASR requires REMEMBER_STT_MODEL and REMEMBER_STT_API_KEY")
        self.url = base_url.rstrip("/") + "/" + path.lstrip("/")
        self.model = model
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio: bytes, content_type: str) -> Transcript:
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime not in FORMATS:
            raise SttFailed("Unsupported audio format for configured ASR")
        # Bound the encoded input before allocating it. The synchronous API has
        # a 10 MiB inline-input budget and rejects recordings longer than 5 min.
        if 4 * ((len(audio) + 2) // 3) + len(mime) + 13 > 10 * 1024 * 1024:
            raise SttFailed("ASR inline audio exceeds the 10 MiB encoded-input limit")
        data = f"data:{mime};base64," + base64.b64encode(audio).decode("ascii")
        body = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": [
                {"type": "input_audio", "input_audio": {"data": data}}
            ]}]},
            "parameters": {"format": FORMATS[mime]},
        }
        try:
            response = httpx.post(
                self.url, json=body,
                headers={"Authorization": f"Bearer {self._api_key}", "X-DashScope-SSE": "disable"},
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise SttTimeout("Configured ASR request timed out") from error
        except httpx.TransportError as error:
            raise SttUnavailable("Configured ASR is unreachable") from error
        if response.status_code in {408, 504}:
            raise SttTimeout("Configured ASR request timed out")
        if response.status_code == 429 or response.status_code >= 500:
            raise SttUnavailable("Configured ASR is temporarily unavailable")
        if not response.is_success:
            raise SttFailed(f"Configured ASR rejected the request (HTTP {response.status_code})")
        try:
            result = response.json()
            output = result.get("output") if isinstance(result, dict) else None
            text = output.get("text") if isinstance(output, dict) else None
            if not isinstance(text, str):
                nested = output.get("output") if isinstance(output, dict) else None
                sentence = nested.get("sentence") if isinstance(nested, dict) else None
                text = sentence.get("text") if isinstance(sentence, dict) else None
        except ValueError as error:
            raise SttFailed("Configured ASR returned invalid JSON") from error
        if not isinstance(text, str):
            raise SttFailed("Configured ASR returned no transcript text")
        return Transcript(text=text, backend=self.backend, model_version=self.model)
