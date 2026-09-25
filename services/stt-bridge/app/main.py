"""A local, provider-isolated STT bridge.

Backend's HttpSttProvider sends raw audio and expects text + model_version.
whisper.cpp's server accepts multipart. This bridge translates that one wire
without putting a vendor dependency or secret in Backend or the iOS app.
"""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MAX_AUDIO_BYTES = 25 * 1024 * 1024


def create_app(
    *,
    whisper_url: str | None = None,
    model_version: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> FastAPI:
    whisper_url = whisper_url or os.environ.get("WHISPER_SERVER_URL", "http://127.0.0.1:8080")
    model_version = model_version or os.environ.get("WHISPER_MODEL_VERSION", "")
    if not model_version.strip() or "fake" in model_version.lower():
        raise RuntimeError("WHISPER_MODEL_VERSION must name a real model revision")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=90)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_client:
            await client.aclose()

    app = FastAPI(title="Remember Me local STT bridge", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model_version": model_version}

    @app.post("/transcribe")
    async def transcribe(request: Request):
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("audio/"):
            return JSONResponse(status_code=415, content={"error": "audio content type required"})
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > MAX_AUDIO_BYTES:
            return JSONResponse(status_code=413, content={"error": "audio too large"})
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_AUDIO_BYTES:
                return JSONResponse(status_code=413, content={"error": "audio too large"})
            chunks.append(chunk)
        audio = b"".join(chunks)
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            return JSONResponse(status_code=413 if audio else 422, content={"error": "invalid audio size"})
        try:
            response = await client.post(
                f"{whisper_url.rstrip('/')}/inference",
                files={"file": ("capture.m4a", audio, content_type)},
                data={"response_format": "json", "language": "auto"},
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException:
            return JSONResponse(status_code=504, content={"error": "STT provider timed out"})
        except httpx.TransportError:
            return JSONResponse(status_code=503, content={"error": "STT provider unavailable"})
        except httpx.HTTPStatusError as error:
            upstream_status = error.response.status_code
            status = 504 if upstream_status == 504 else 503 if upstream_status in (429, 503) else 502
            return JSONResponse(status_code=status, content={"error": "STT provider refused audio"})
        except ValueError:
            return JSONResponse(status_code=502, content={"error": "STT provider response invalid"})
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or not text.strip():
            return JSONResponse(status_code=422, content={"error": "STT returned no speech"})
        return {"text": text.strip(), "model_version": model_version}

    return app


# Importing the app requires an explicit real model revision; this prevents a
# service that advertises a fake identity from appearing ready to Backend.
app = create_app() if os.environ.get("WHISPER_MODEL_VERSION") else None
