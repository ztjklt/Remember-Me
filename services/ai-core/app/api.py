"""Thin HTTP transport for the provider-neutral AI Core."""

from __future__ import annotations

from contextlib import asynccontextmanager
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .calibration import CalibrationAssessment, CalibrationAssessor, CalibrationInput
from .capture_planner import CapturePlanner, PlannerInput, PlannerOutput
from .config import Settings
from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid, EvidenceInvalid, ProviderTimeout, ProviderUnavailable
from .extractor import MemoryExtractor
from .limits import RequestSizeLimit
from .providers.fixture import FixtureProvider
from .providers.calibration_http import HttpComparisonProvider
from .providers.openai_compatible import OpenAICompatibleProvider
from .providers.ollama_local import OllamaLocalProvider
from .persona import PersonaInput, PersonaOutput, PersonaSynthesizer
from .twin import TwinInput, TwinSynthesis, TwinSynthesizer
from .twin_agent import TwinAgent, TwinAgentInput, TwinAgentOutput


def _build_extractor(settings: Settings) -> MemoryExtractor:
    if settings.provider == "fixture":
        if settings.environment not in {"development", "test"}:
            raise ValueError("fixture provider is allowed only in development and test")
        provider = FixtureProvider()
    elif settings.provider == "ollama_local":
        provider = OllamaLocalProvider(
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        )
    else:
        provider = OpenAICompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
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


def _build_assessor(settings: Settings) -> CalibrationAssessor | None:
    if settings.provider == "fixture":
        return None
    return CalibrationAssessor(
        provider=HttpComparisonProvider(
            kind=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        ),
        model_version=settings.model_version,
    )


def _build_twin(settings: Settings) -> TwinSynthesizer | None:
    if settings.provider == "fixture":
        return None
    return TwinSynthesizer(
        provider=HttpComparisonProvider(
            kind=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        ),
        model_version=settings.model_version,
    )


def _build_persona(settings: Settings) -> PersonaSynthesizer | None:
    if settings.provider == "fixture":
        return None
    return PersonaSynthesizer(
        provider=HttpComparisonProvider(
            kind=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        ),
        model_version=settings.model_version,
    )


def _build_twin_agent(settings: Settings) -> TwinAgent | None:
    if settings.provider == "fixture":
        return None
    return TwinAgent(
        provider=HttpComparisonProvider(
            kind=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        ),
        model_version=settings.model_version,
    )


def _build_capture_planner(settings: Settings) -> CapturePlanner | None:
    if settings.provider == "fixture":
        return None
    return CapturePlanner(
        provider=HttpComparisonProvider(
            kind=settings.provider,
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key.get_secret_value(),
            structured_output_mode=settings.structured_output_mode,
            timeout_seconds=settings.timeout_seconds,
            max_response_bytes=settings.max_response_bytes,
        ),
        model_version=settings.model_version,
    )


def create_app(
    settings: Settings | None = None,
    *,
    extractor: MemoryExtractor | None = None,
    assessor: CalibrationAssessor | None = None,
    twin_synthesizer: TwinSynthesizer | None = None,
    persona_synthesizer: PersonaSynthesizer | None = None,
    twin_agent: TwinAgent | None = None,
    capture_planner: CapturePlanner | None = None,
) -> FastAPI:
    settings = settings or Settings()
    active_extractor = extractor or _build_extractor(settings)
    active_assessor = assessor or _build_assessor(settings)
    active_twin = twin_synthesizer or _build_twin(settings)
    active_persona = persona_synthesizer or _build_persona(settings)
    active_twin_agent = twin_agent or _build_twin_agent(settings)
    active_capture_planner = capture_planner or _build_capture_planner(settings)
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
            if assessor is None and active_assessor is not None:
                active_assessor.provider.close()
            if twin_synthesizer is None and active_twin is not None:
                active_twin.provider.close()
            if persona_synthesizer is None and active_persona is not None:
                active_persona.provider.close()
            if twin_agent is None and active_twin_agent is not None:
                active_twin_agent.provider.close()
            if capture_planner is None and active_capture_planner is not None:
                active_capture_planner.provider.close()

    app = FastAPI(title="Remember Me AI Core", version="0.2.0", lifespan=lifespan)
    app.add_middleware(RequestSizeLimit, max_bytes=settings.max_request_bytes)

    @app.exception_handler(RequestValidationError)
    async def input_invalid_handler(_request, exc: RequestValidationError) -> JSONResponse:
        # Default FastAPI errors can echo the full private transcript on a missing
        # field, and arbitrary user keys can appear in loc. Keep safe field hints.
        known_fields = {"body", *AICoreInput.model_fields, *CalibrationInput.model_fields,
                        *TwinInput.model_fields, *PersonaInput.model_fields,
                        *TwinAgentInput.model_fields, *PlannerInput.model_fields}
        details = [{
            "type": error["type"],
            "loc": [part if isinstance(part, int) or part in known_fields else "unknown_field"
                    for part in error["loc"]],
            "msg": "Invalid request field",
        } for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": details})

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

    @app.post("/calibrate", response_model=CalibrationAssessment)
    def calibrate(payload: CalibrationInput) -> CalibrationAssessment:
        if active_assessor is None:
            raise ProviderUnavailable("A real comparison provider is required")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core comparison capacity is busy")
        try:
            return active_assessor.assess(payload)
        finally:
            slots.release()

    @app.post("/twin/simulate", response_model=TwinSynthesis)
    def simulate_twin(payload: TwinInput) -> TwinSynthesis:
        if active_twin is None:
            raise ProviderUnavailable("A real Twin provider is required")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core Twin capacity is busy")
        try:
            return active_twin.synthesize(payload)
        finally:
            slots.release()

    @app.post("/persona/reconcile", response_model=PersonaOutput)
    def reconcile_persona(payload: PersonaInput) -> PersonaOutput:
        if active_persona is None:
            raise ProviderUnavailable("A real Persona provider is required")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core Persona capacity is busy")
        try:
            return active_persona.synthesize(payload)
        finally:
            slots.release()

    @app.post("/twin/answer", response_model=TwinAgentOutput)
    def answer_twin(payload: TwinAgentInput) -> TwinAgentOutput:
        if active_twin_agent is None:
            raise ProviderUnavailable("A real Twin Agent provider is required")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core Twin capacity is busy")
        try:
            return active_twin_agent.answer(payload)
        finally:
            slots.release()

    @app.post("/capture/plan", response_model=PlannerOutput)
    def plan_capture(payload: PlannerInput) -> PlannerOutput:
        if active_capture_planner is None:
            raise ProviderUnavailable("A real Capture Planner provider is required")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core Capture Planner capacity is busy")
        try:
            return active_capture_planner.plan(payload)
        finally:
            slots.release()

    return app


__all__ = ["create_app"]
