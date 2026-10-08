"""Loopback-only Whisper sidecar for the single-user Mac deployment.

Run with `uv run uvicorn app.local_stt:app --host 127.0.0.1 --port 8200`.
"""

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .faster_stt import FasterWhisperEngine, LocalSttError

app = FastAPI(title="Remember Me local STT")
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MODEL_PATH = Path(os.environ.get("WHISPER_MODEL_PATH", str(Path.home() / ".cache/remember-me/ggml-base.bin")))
_inference_slot = Lock()


def transcribe_audio(audio: bytes, model_path: Path = MODEL_PATH) -> dict[str, str]:
    if not model_path.is_file():
        raise RuntimeError("Multilingual Whisper model is missing")
    if ".en." in model_path.name:
        raise RuntimeError("An English-only Whisper model cannot transcribe Chinese")
    with TemporaryDirectory(prefix="remember-stt-") as folder:
        root = Path(folder)
        source = root / "capture.m4a"
        wav = root / "capture.wav"
        output = root / "transcript"
        source.write_bytes(audio)
        try:
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
                 "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)],
                check=True, capture_output=True, timeout=60,
            )
            subprocess.run(
                ["whisper-cli", "-m", str(model_path), "-l", "zh", "-f", str(wav),
                 "-otxt", "-of", str(output), "-np", "-nt"],
                check=True, capture_output=True, timeout=240,
            )
        except subprocess.TimeoutExpired as exc:
            raise LocalSttError("Local transcription timed out", 504) from exc
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError("Audio conversion or Whisper failed") from exc
        text = output.with_suffix(".txt").read_text(encoding="utf-8").strip()
        # Hash the actual model file, not merely its filename. Model provenance
        # stays meaningful when a local operator replaces the weights in place.
        with model_path.open("rb") as model_file:
            digest = hashlib.file_digest(model_file, "sha256").hexdigest()[:12]
        return {"text": text, "model_version": f"whisper-{model_path.stem}-{digest}"}


@lru_cache(maxsize=1)
def _engine():
    engine = os.environ.get("REMEMBER_LOCAL_STT_ENGINE", "whisper_cpp")
    if engine == "whisper_cpp":
        return transcribe_audio
    if engine == "faster_whisper":
        path = os.environ.get("REMEMBER_FASTER_WHISPER_MODEL_PATH")
        if not path:
            raise LocalSttError("REMEMBER_FASTER_WHISPER_MODEL_PATH is required")
        adapter = FasterWhisperEngine(
            Path(path).expanduser(),
            device=os.environ.get("REMEMBER_LOCAL_STT_DEVICE", "cpu"),
            compute_type=os.environ.get("REMEMBER_LOCAL_STT_COMPUTE_TYPE", "int8"),
        )
        return adapter.transcribe
    raise LocalSttError("Unsupported local transcription engine")


@app.get("/health")
def health() -> dict[str, str]:
    # Liveness, not a claim that weights or inference have been verified.
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    if not request.headers.get("content-type", "").split(";", 1)[0].strip().lower().startswith("audio/"):
        raise HTTPException(415, "An audio content type is required")
    if not _inference_slot.acquire(blocking=False):
        raise HTTPException(503, "Local transcription is busy", headers={"Retry-After": "1"})
    try:
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                raise HTTPException(413, "Audio is too large")
            chunks.append(chunk)
        audio = b"".join(chunks)
        if not audio:
            raise HTTPException(422, "Audio is empty")
        return await run_in_threadpool(_engine(), audio)
    except LocalSttError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, "The local transcription engine is unavailable") from exc
    finally:
        _inference_slot.release()
