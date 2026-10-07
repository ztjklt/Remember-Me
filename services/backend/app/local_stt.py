"""Loopback-only Whisper sidecar; raw ASR remains separate from display script.

Run with `uv run uvicorn app.local_stt:app --host 127.0.0.1 --port 8200`.
"""

import hashlib
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

app = FastAPI(title="Remember Me local STT")
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MODEL_PATH = Path(os.environ.get("WHISPER_MODEL_PATH", str(Path.home() / ".cache/remember-me/ggml-base.bin")))
SIMPLIFIED_PROMPT = "以下是普通话的句子，使用简体中文。"


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
                 "--prompt", SIMPLIFIED_PROMPT, "-otxt", "-of", str(output), "-np", "-nt"],
                check=True, capture_output=True, timeout=240,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError("Audio conversion or Whisper failed") from exc
        text = output.with_suffix(".txt").read_text(encoding="utf-8").strip()
        # Hash the actual model file, not merely its filename. Model provenance
        # stays meaningful when a local operator replaces the weights in place.
        with model_path.open("rb") as model_file:
            digest = hashlib.file_digest(model_file, "sha256").hexdigest()[:12]
        return {"text": text, "model_version": f"whisper-{model_path.stem}-{digest}-zh-hans-p1"}


@app.post("/transcribe")
async def transcribe(request: Request) -> dict[str, str]:
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio is too large")
        chunks.append(chunk)
    audio = b"".join(chunks)
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio is empty or too large")
    try:
        return await run_in_threadpool(transcribe_audio, audio)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
