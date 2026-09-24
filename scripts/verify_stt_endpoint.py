"""Check that a configured STT endpoint speaks Backend's raw-audio HTTP wire.

Run with Backend's locked Python environment:

    cd services/backend
    uv run --locked python ../../scripts/verify_stt_endpoint.py

This checks endpoint compatibility and a recognition spot check. It does not
create an Episode or complete the Android Phase 1 gate.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import mimetypes
import os
from pathlib import Path
import sys
from time import monotonic

import httpx


MAX_AUDIO_BYTES = 25 * 1024 * 1024


class SttCheckFailed(Exception):
    """A safe, transcript-free reason the endpoint cannot be certified."""


@dataclass(frozen=True)
class SttCheckResult:
    model_version: str
    text_chars: int
    elapsed_seconds: float
    expected_phrase_checked: bool


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SttCheckFailed(f"Set {name} before running the STT check")
    return value


def audio_input() -> tuple[bytes, str]:
    path = Path(required("PHASE1_AUDIO_PATH")).expanduser().resolve()
    if not path.is_file():
        raise SttCheckFailed("PHASE1_AUDIO_PATH must be an existing audio file")
    content_type = {".m4a": "audio/mp4", ".wav": "audio/wav"}.get(
        path.suffix.lower(), mimetypes.guess_type(path.name)[0]
    )
    if content_type is None or not content_type.startswith("audio/"):
        raise SttCheckFailed("Audio file needs a recognized audio extension")
    if path.stat().st_size == 0 or path.stat().st_size > MAX_AUDIO_BYTES:
        raise SttCheckFailed("Audio file must be nonempty and at most 25 MiB")
    audio = path.read_bytes()
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise SttCheckFailed("Audio file changed or exceeds the 25 MiB limit")
    return audio, content_type


def endpoint(base_url: str, path: str) -> str:
    try:
        parsed = httpx.URL(base_url)
    except httpx.InvalidURL as error:
        raise SttCheckFailed("REMEMBER_STT_URL must be a valid HTTP(S) base URL") from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise SttCheckFailed("REMEMBER_STT_URL must be an HTTP(S) base URL")
    if parsed.userinfo or parsed.query or parsed.fragment:
        raise SttCheckFailed("REMEMBER_STT_URL must not contain credentials or a query")
    if not path.startswith("/") or "?" in path or "#" in path:
        raise SttCheckFailed("REMEMBER_STT_PATH must be an absolute URL path")
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def verify(
    *,
    url: str,
    audio: bytes,
    content_type: str,
    timeout_seconds: float,
    expected_fragment: str | None = None,
    client: httpx.Client,
) -> SttCheckResult:
    started = monotonic()
    try:
        response = client.post(
            url,
            content=audio,
            headers={"Content-Type": content_type},
            timeout=timeout_seconds,
            follow_redirects=False,
        )
    except httpx.TimeoutException as error:
        raise SttCheckFailed("STT endpoint timed out") from error
    except httpx.TransportError as error:
        raise SttCheckFailed("STT endpoint connection failed") from error
    elapsed = monotonic() - started
    if response.status_code != 200:
        raise SttCheckFailed(f"STT endpoint returned HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError as error:
        raise SttCheckFailed("STT endpoint returned invalid JSON") from error
    if not isinstance(body, dict):
        raise SttCheckFailed("STT endpoint JSON must be an object")
    transcript = body.get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise SttCheckFailed("STT endpoint returned no transcript text")
    if transcript.lstrip().startswith("[fake-stt]"):
        raise SttCheckFailed("STT endpoint returned Backend's fake transcript")
    model_version = body.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        raise SttCheckFailed("STT endpoint did not report a model version")
    model_version = model_version.strip()
    if model_version.startswith("fake-stt-"):
        raise SttCheckFailed("STT endpoint reported a fake model version")
    if expected_fragment and expected_fragment.casefold() not in transcript.casefold():
        raise SttCheckFailed("Expected spoken phrase was absent from the transcript")
    return SttCheckResult(
        model_version=model_version,
        text_chars=len(transcript),
        elapsed_seconds=elapsed,
        expected_phrase_checked=bool(expected_fragment),
    )


def main() -> None:
    url = endpoint(required("REMEMBER_STT_URL"), required("REMEMBER_STT_PATH"))
    audio, content_type = audio_input()
    try:
        timeout_seconds = float(os.environ.get("REMEMBER_STT_TIMEOUT_SECONDS", "60"))
    except ValueError as error:
        raise SttCheckFailed("REMEMBER_STT_TIMEOUT_SECONDS must be numeric") from error
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise SttCheckFailed("REMEMBER_STT_TIMEOUT_SECONDS must be positive and finite")
    expected_fragment = os.environ.get("PHASE1_EXPECTED_TEXT_FRAGMENT", "").strip() or None

    with httpx.Client() as client:
        result = verify(
            url=url,
            audio=audio,
            content_type=content_type,
            timeout_seconds=timeout_seconds,
            expected_fragment=expected_fragment,
            client=client,
        )
    safe_version = "".join(
        char for char in result.model_version if char.isprintable() and char not in "\r\n"
    )[:100]
    print(
        f"stt=ready audio_bytes={len(audio)} text_chars={result.text_chars}"
        f" model_version={safe_version} elapsed_seconds={result.elapsed_seconds:.1f}"
        f" expected_phrase={'pass' if result.expected_phrase_checked else 'not_checked'}"
    )


if __name__ == "__main__":
    try:
        main()
    except SttCheckFailed as error:
        print(f"STT check failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
