"""Thin HTTP transport for the provider-neutral AI Core."""

from __future__ import annotations

from contextlib import asynccontextmanager
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid, EvidenceInvalid, ProviderTimeout, ProviderUnavailable
from .extractor import MemoryExtractor
from .errors import ProviderAuthenticationFailed
from .profile_proposals import ProfileProposalInput, ProfileProposalOutput, ProfileProposalProvider
from .profile_relations import RelationInput, RelationOutput
from .providers.weixin import WeixinProvider, WeixinChat, WeixinTwinProvider, WeixinCalibrationProvider
from .limits import RequestSizeLimit
from .providers.fixture import FixtureProvider
from .providers.deepseek import DeepSeekProvider
from .providers.openai_compatible import OpenAICompatibleProvider
from .providers.ollama import OllamaProvider
from .twin import DeepSeekTwinProvider, TwinInput, TwinOutput
from .calibration import DeepSeekCalibrationProvider, CalibrationInput, CalibrationOutput

def _build_extractor(settings: Settings) -> MemoryExtractor:
    if settings.provider == "fixture":
        if settings.environment not in {"development", "test"}:
            raise ValueError("fixture provider is allowed only in development and test")
        provider = FixtureProvider()
    elif settings.provider == "ollama":
        provider = OllamaProvider(base_url=settings.base_url, timeout_seconds=settings.timeout_seconds,
                                  max_response_bytes=settings.max_response_bytes)
    elif settings.provider == "weixin":
        provider = WeixinProvider(api_key=settings.weixin_api_key.get_secret_value())
    elif settings.provider == "deepseek":
        provider = DeepSeekProvider(base_url=settings.base_url,
                                    api_key=settings.api_key.get_secret_value(),
                                    timeout_seconds=settings.timeout_seconds,
                                    max_response_bytes=settings.max_response_bytes)
    else:
        provider = OpenAICompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key.get_secret_value(),
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        )

    return MemoryExtractor(
        provider=provider,
        model=settings.model,
        model_version=settings.model_version,
        prompt_version=settings.prompt_version,
        schema_version=settings.schema_version,
    )

def _safe_error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "error_message": message},
    )

def create_app(
    settings: Settings | None = None,
    *,
    extractor: MemoryExtractor | None = None,
    twin_provider: DeepSeekTwinProvider | None = None,
    calibration_provider: DeepSeekCalibrationProvider | None = None,
    profile_provider: ProfileProposalProvider | None = None,
) -> FastAPI:
    settings = settings or Settings()
    active_extractor = extractor or _build_extractor(settings)
    active_twin = twin_provider or (DeepSeekTwinProvider(
        base_url=settings.base_url, api_key=settings.api_key.get_secret_value(),
        model=settings.model, timeout_seconds=settings.timeout_seconds,
    ) if settings.provider == "deepseek" else None)
    active_calibration = calibration_provider or (DeepSeekCalibrationProvider(
        base_url=settings.base_url, api_key=settings.api_key.get_secret_value(),
        model=settings.model, timeout_seconds=settings.timeout_seconds,
    ) if settings.provider == "deepseek" else None)
    active_profile = profile_provider
    if settings.provider == "weixin":
        key = settings.weixin_api_key.get_secret_value()
        active_twin = twin_provider or WeixinTwinProvider(api_key=key, focus_hints=settings.twin_focus_hints)
        active_calibration = calibration_provider or WeixinCalibrationProvider(api_key=key)
        active_profile = profile_provider or ProfileProposalProvider(WeixinChat(api_key=key))
    slots = BoundedSemaphore(settings.max_concurrent_requests)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            # Injected extractors/clients remain owned by their caller.
            if extractor is None:
                close = getattr(active_extractor.provider, "close", None)
                if close is not None:
                    close()
            if twin_provider is None and active_twin is not None:
                active_twin.close()
            if profile_provider is None and active_profile is not None:
                active_profile.close()
            if calibration_provider is None and active_calibration is not None:
                active_calibration.close()

    app = FastAPI(title="Remember Me AI Core", version="0.2.0", lifespan=lifespan)
    app.add_middleware(RequestSizeLimit, max_bytes=settings.max_request_bytes)

    @app.exception_handler(RequestValidationError)
    async def input_invalid_handler(_request, exc: RequestValidationError) -> JSONResponse:
        # Default FastAPI errors can echo the full private transcript on a missing
        # field, and arbitrary user keys can appear in loc. Keep safe field hints.
        known_fields = {"body", *AICoreInput.model_fields}
        details = [{
            "type": error["type"],
            "loc": [part if isinstance(part, int) or part in known_fields else "unknown_field"
                    for part in error["loc"]],
            "msg": "Invalid request field",
        } for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(ProviderAuthenticationFailed)
    async def auth_failed_handler(_request, exc):
        return _safe_error(exc.code, "AI provider authentication failed", 502)

    @app.exception_handler(ProviderTimeout)
    async def provider_timeout_handler(_request, exc: ProviderTimeout) -> JSONResponse:
        return _safe_error(exc.code, "AI Core provider timed out", 504)

    @app.exception_handler(ProviderUnavailable)
    async def provider_unavailable_handler(_request, exc: ProviderUnavailable) -> JSONResponse:
        return _safe_error(exc.code, "AI Core provider is unavailable", 503)

    @app.exception_handler(AIOutputInvalid)
    async def output_invalid_handler(_request, exc: AIOutputInvalid) -> JSONResponse:
        return _safe_error(exc.code, "AI Core returned invalid structured output", 502)

    @app.exception_handler(EvidenceInvalid)
    async def evidence_invalid_handler(_request, exc: EvidenceInvalid) -> JSONResponse:
        return _safe_error(exc.code, "AI Core returned invalid provenance", 502)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/process", response_model=AICoreOutput, response_model_exclude_none=True)
    def process(payload: AICoreInput) -> AICoreOutput:
        # FastAPI runs synchronous routes in its worker pool; the model must not
        # block the event loop that serves liveness and other incoming requests.
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core extraction capacity is busy")
        try:
            return active_extractor.process(payload)
        finally:
            slots.release()

    @app.post("/twin", response_model=TwinOutput)
    def answer_twin(payload: TwinInput) -> TwinOutput:
        if active_twin is None:
            raise ProviderUnavailable("Twin requires the configured DeepSeek adapter")
        # Interactive requests may wait briefly behind background proposals.
        # Still one actual provider call, bounded total wait, no hidden retry.
        if not slots.acquire(timeout=15):
            raise ProviderUnavailable("AI Core capacity is busy")
        try:
            return active_twin.answer(payload)
        finally:
            slots.release()

    @app.post("/calibrate", response_model=CalibrationOutput)
    def calibrate(payload: CalibrationInput) -> CalibrationOutput:
        if active_calibration is None:
            raise ProviderUnavailable("Calibration requires the configured DeepSeek adapter")
        if not slots.acquire(timeout=15):
            raise ProviderUnavailable("AI Core capacity is busy")
        try:
            return active_calibration.compare(payload)
        finally:
            slots.release()

    @app.post("/profile-proposals", response_model=ProfileProposalOutput)
    def profile_proposals(payload: ProfileProposalInput):
        if active_profile is None:
            raise ProviderUnavailable("Profile proposals require a configured provider")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core capacity is busy")
        try:
            return active_profile.propose(payload)
        finally:
            slots.release()

    @app.post('/profile-relations',response_model=RelationOutput)
    def profile_relations(payload: RelationInput):
        if active_profile is None:
            raise ProviderUnavailable('Profile relations require a configured provider')
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable('AI Core capacity is busy')
        try:
            return active_profile.propose_relations(payload)
        finally:
            slots.release()

    return app

__all__ = ["create_app"]
