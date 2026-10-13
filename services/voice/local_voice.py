"""Mac-only Qwen3-TTS voice cloning adapter. Bind this process to 127.0.0.1."""

from __future__ import annotations

import io
import os
import subprocess
import wave
from array import array
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

app = FastAPI(title="Remember Me local voice")
MODEL = os.environ.get("REMEMBER_VOICE_MODEL", "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")
MODEL_REVISION = "1eccf1cb2519b5a4e8a95b5f0544f3303568164f"
MODEL_VERSION = MODEL + "@" + MODEL_REVISION if MODEL == "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16" else MODEL
MAX_SAMPLE_BYTES = 8 * 1024 * 1024


def _sample_wav(sample: bytes, folder: Path) -> tuple[Path, float]:
    if not sample or len(sample) > MAX_SAMPLE_BYTES:
        raise ValueError("声音样本需在 8 MB 以内。")
    source = folder / "sample.m4a"
    target = folder / "sample.wav"
    source.write_bytes(sample)
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(source),
                        "-ac", "1", "-ar", "24000", "-f", "wav", str(target)],
                       check=True, capture_output=True, timeout=40)
        with wave.open(str(target), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
            if audio.getsampwidth() != 2:
                raise ValueError("声音样本格式不受支持。")
            samples = array("h", audio.readframes(audio.getnframes()))
        if not 5 <= duration <= 15:
            raise ValueError("请录制 5 到 15 秒的自然说话声音。")
        energy = (sum(int(value) ** 2 for value in samples) / max(1, len(samples))) ** 0.5
        if energy < 180:
            raise ValueError("样本声音太轻或几乎无声，请重新录制。")
    except (OSError, subprocess.SubprocessError, wave.Error) as exc:
        raise ValueError("声音样本无法读取，请重新录制。") from exc
    return target, duration


@lru_cache(maxsize=1)
def _model():
    from mlx_audio.tts.utils import load_model
    if MODEL == "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16":
        from huggingface_hub import snapshot_download
        return load_model(snapshot_download(MODEL, revision=MODEL_REVISION))
    return load_model(MODEL)


def synthesize_audio(sample: bytes, reference_text: str, text: str) -> bytes:
    with TemporaryDirectory(prefix="remember-voice-") as name:
        reference, _ = _sample_wav(sample, Path(name))
        results = list(_model().generate(text=text, ref_audio=str(reference), ref_text=reference_text))
        if not results:
            raise RuntimeError("声音模型没有生成结果。")
        import numpy as np
        import soundfile as sf
        samples = np.concatenate([np.asarray(result.audio, dtype=np.float32).reshape(-1)
                                  for result in results])
        if samples.size == 0 or not np.isfinite(samples).all():
            raise RuntimeError("声音模型生成了无效音频。")
        out = io.BytesIO()
        sf.write(out, samples, int(getattr(_model(), "sample_rate", 24000)), format="WAV")
        return out.getvalue()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_VERSION}


@app.post("/validate")
async def validate(request: Request) -> dict:
    sample = await request.body()
    try:
        with TemporaryDirectory(prefix="remember-voice-check-") as name:
            _, duration = await run_in_threadpool(_sample_wav, sample, Path(name))
        return {"duration_seconds": round(duration, 2), "model_version": MODEL_VERSION}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/synthesize")
async def synthesize(text: str = Form(...), reference_text: str = Form(...),
                     sample: UploadFile = File(...)) -> Response:
    if not text.strip() or len(text) > 500 or not reference_text.strip() or len(reference_text) > 1000:
        raise HTTPException(422, "文字为空或过长。")
    audio = await sample.read(MAX_SAMPLE_BYTES + 1)
    try:
        output = await run_in_threadpool(synthesize_audio, audio, reference_text.strip(), text.strip())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, "本机声音模型未能完成生成。") from exc
    return Response(content=output, media_type="audio/wav", headers={"X-Model-Version": MODEL_VERSION})
