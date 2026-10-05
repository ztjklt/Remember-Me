"""Demo-only console; the normal Backend entrypoint exposes no session file."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


def attach_console(backend, session_file, mode):
    console = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @console.middleware("http")
    async def local_only(request: Request, call_next):
        origin = f"{request.url.scheme}://{request.url.netloc}"
        if request.url.hostname not in {"localhost", "127.0.0.1", "::1"} or (
            request.headers.get("origin", origin) != origin
        ):
            return JSONResponse({"detail": "Local console only"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; media-src 'self' blob:; "
            "object-src 'none'; frame-ancestors 'none'; form-action 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @console.get("/session")
    def session():
        try:
            data = json.loads(Path(session_file).read_text())
            return {"mode": mode, **{key: data[key] for key in (
                "actor_token", "subject_id", "recording_consent_id"
            )}}
        except (OSError, ValueError, KeyError, TypeError):
            return JSONResponse({"detail": "Demo session unavailable"}, status_code=404)

    console.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True))
    backend.mount("/debug/agent", console)
    return backend


def create_app():
    from app.main import app
    return attach_console(app, os.environ["REMEMBER_DEMO_SESSION_FILE"],
                          os.environ["REMEMBER_DEMO_MODE"])
