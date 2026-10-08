import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import __version__
from .ai_core import build_ai_client
from .api import consents, episodes, health, session, person_model, pairing, twin, voice, calibration, workbench
from .config import Settings, get_settings
from .db import Database
from .errors import REQUEST_INVALID, AppError
from .logging_config import configure_logging, trace_id_var
from .storage import build_object_store
from .stt import build_stt_provider
from .retrieval import LocalEncoder
from .twin_client import TwinClient
from .voice_client import VoiceClient
from .calibration_client import CalibrationClient

access_logger = logging.getLogger("app.access")


class RequestContextMiddleware:
    """Attach a trace id to every request and emit one structured access log.

    The trace id is generated here, at the request boundary, and is the value
    Issue #1 propagates as the contract's trace_id (ADR-0001 D13).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = uuid4().hex
        token = trace_id_var.set(trace_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            access_logger.info(
                "request.completed",
                extra={
                    "extra_fields": {
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                },
            )
            trace_id_var.reset(token)


async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    """HTTP-level error envelope.

    Backend-owned rather than contract-defined: the contract fixes error_code and
    error_message on Processing Status, and this reuses those names for
    request-level failures instead of inventing competing ones. Codes come from
    app/errors.py.
    """
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "error_code": exc.code,
            "error_message": exc.message,
            "request_id": trace_id_var.get(),
        },
    )


def _validation_message(exc: RequestValidationError) -> str:
    """One readable line naming the offending fields.

    Only loc and msg are copied out: pydantic puts exception objects in `ctx`,
    which would not survive JSON serialization.
    """
    parts = []
    for error in exc.errors()[:5]:
        location = ".".join(str(part) for part in error.get("loc", ())[1:])
        message = str(error.get("msg", "invalid"))
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts)


async def _request_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Malformed requests get the same envelope as rejected operations.

    Without this, a bad body would return FastAPI's default shape while every
    other failure returned ours, and a client would need two parsers.
    """
    return JSONResponse(
        status_code=422,
        content={
            "error_code": REQUEST_INVALID,
            "error_message": _validation_message(exc),
            "request_id": trace_id_var.get(),
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    database = Database(settings.database_url)
    object_store = build_object_store(settings)
    # Built here, although the API process does not run them, so that a provider
    # this environment is not allowed to use fails at startup rather than in the
    # worker long after the deployment looked healthy.
    stt_provider = build_stt_provider(settings)
    ai_client = build_ai_client(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        database.dispose()

    app = FastAPI(
        title="Remember Me Backend",
        version=__version__,
        summary="Phase 1 service foundation. See docs/architecture/backend-adr.md.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.object_store = object_store
    app.state.stt_provider = stt_provider
    app.state.ai_client = ai_client
    app.state.embedding_encoder = LocalEncoder(settings.embedding_model)
    app.state.twin_client = TwinClient(settings.ai_core_url, settings.ai_timeout_seconds)
    app.state.voice_client = VoiceClient(settings.voice_url, settings.voice_timeout_seconds)
    app.state.calibration_client = CalibrationClient(settings.ai_core_url, settings.ai_timeout_seconds)

    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _request_error_handler)
    app.include_router(health.router)
    app.include_router(session.router)
    from .api import accounts
    app.include_router(accounts.router)
    app.include_router(consents.router)
    app.include_router(episodes.router)
    app.include_router(person_model.router)
    app.include_router(pairing.router)
    app.include_router(twin.router)
    app.include_router(voice.router)
    app.include_router(calibration.router)
    app.include_router(workbench.router)
    from .api import profiles
    from .profiles import ProfileClient
    app.state.profile_client = ProfileClient(settings.ai_core_url, settings.ai_timeout_seconds)
    app.include_router(profiles.router)
    if settings.enable_workbench:
        from pathlib import Path
        from fastapi.staticfiles import StaticFiles
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
        app.mount('/workbench', StaticFiles(directory=Path(__file__).parent / 'workbench', html=True), name='workbench')
        # Design-only assets from reviewed PR85; no prototype fixtures/audio or
        # repository root is exposed by the live application.
        brand = Path(__file__).resolve().parents[3] / 'assets' / 'brand' / 'forget-me-not'
        if brand.is_dir():
            app.mount('/brand', StaticFiles(directory=brand), name='brand')
    return app


app = create_app()
