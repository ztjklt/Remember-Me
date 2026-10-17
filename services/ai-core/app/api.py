"""Thin HTTP transport for the provider-neutral AI Core."""

from __future__ import annotations

from contextlib import asynccontextmanager, nullcontext
from threading import BoundedSemaphore
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid, EvidenceInvalid, ProviderTimeout, ProviderUnavailable
from .extractor import MemoryExtractor
from .errors import ProviderAuthenticationFailed
from .profile_proposals import ProfileProposalInput, ProfileProposalOutput, ProfileProposalProvider
from .profile_relations import RelationInput, RelationOutput
from .narrative import NarrativeInput
from .expression import ExpressionInput, ExpressionProvider
from .persona import PersonaInput, PersonaOutput, PersonaProvider
from .conversation import ConversationInput, respond as conversation_reply
from .providers.weixin import WeixinProvider, WeixinChat, WeixinTwinProvider, WeixinCalibrationProvider
from .limits import RequestSizeLimit
from .providers.fixture import FixtureProvider
from .providers.deepseek import DeepSeekProvider
from .providers.openai_compatible import OpenAICompatibleProvider
from .providers.ollama import OllamaProvider
from .twin import DeepSeekTwinProvider, TwinInput, TwinOutput
from .calibration import DeepSeekCalibrationProvider, CalibrationInput, CalibrationOutput
from .transcript_correction import CorrectionInput, CorrectionOutput, TranscriptCorrector

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
    persona_provider: PersonaProvider | None = None,
    transcript_corrector: TranscriptCorrector | None = None,
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
    active_persona = persona_provider
    active_corrector = transcript_corrector
    if settings.provider == "weixin":
        key = settings.weixin_api_key.get_secret_value()
        active_corrector = transcript_corrector or TranscriptCorrector(active_extractor.provider)
        active_twin = twin_provider or WeixinTwinProvider(api_key=key, focus_hints=settings.twin_focus_hints, verify_answers=settings.twin_verify_answers, structured_answers=settings.twin_structured_answers, quote_answers=settings.twin_quote_answers)
        active_calibration = calibration_provider or WeixinCalibrationProvider(api_key=key)
        active_profile = profile_provider or ProfileProposalProvider(WeixinChat(api_key=key),verify_candidates=settings.profile_verify_candidates)
        active_persona = persona_provider or PersonaProvider(WeixinChat(api_key=key),
            total_timeout_seconds=settings.persona_total_timeout_seconds,
            call_timeout_seconds=settings.persona_call_timeout_seconds,
            fictional_debug_trace=settings.persona_fictional_debug_trace)
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
            if persona_provider is None and active_persona is not None:
                active_persona.close()

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

    @app.post("/transcripts/correct", response_model=CorrectionOutput)
    def correct_transcript(payload: CorrectionInput):
        if active_corrector is None:
            raise ProviderUnavailable("Transcript correction requires a configured provider")
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable("AI Core correction capacity is busy")
        try:
            return active_corrector.correct(payload)
        finally:
            slots.release()

    @app.post("/twin", response_model=TwinOutput)
    async def answer_twin(payload: TwinInput, request: Request) -> TwinOutput:
        if payload.voice_response:
            from .cancellation import until_disconnect
            return await until_disconnect(request,lambda: run_twin(payload))
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(run_twin,payload)

    @app.post('/conversation')
    async def conversation(payload: ConversationInput, request: Request):
        from .cancellation import until_disconnect
        def run():
            if active_persona is None or not slots.acquire(timeout=2):
                raise ProviderUnavailable('Conversation temporarily unavailable')
            try:
                chat=active_persona.chat
                with (chat.transport_scope(timeout_seconds=settings.voice_call_timeout_seconds,
                      json_retry_after_seconds=settings.effective_voice_json_retry_after_seconds,
                      **({'json_hedged':True} if settings.voice_json_hedged else {}))
                      if hasattr(chat,'transport_scope') else nullcontext()):
                    return conversation_reply(chat,payload)
            finally: slots.release()
        return await until_disconnect(request,run)

    def run_twin(payload):
        from .voice_stream import generation_streamed
        if active_twin is None:
            raise ProviderUnavailable("Twin requires the configured DeepSeek adapter")
        # Interactive requests may wait briefly behind background proposals.
        # Still one actual provider call, bounded total wait, no hidden retry.
        if not slots.acquire(timeout=15):
            raise ProviderUnavailable("AI Core capacity is busy")
        try:
            policy={'retry_after_seconds':settings.voice_retry_after_seconds} if generation_streamed.get() and settings.voice_retry_after_seconds>0 else {}
            with (active_twin.transport_scope(timeout_seconds=settings.voice_call_timeout_seconds,
                  json_retry_after_seconds=settings.effective_voice_json_retry_after_seconds,
                  **({'json_hedged':True} if settings.voice_json_hedged else {}),**policy)
                  if payload.voice_response and hasattr(active_twin,'transport_scope') else nullcontext()):
                return active_twin.answer(payload)
        finally:
            slots.release()

    @app.post('/twin/voice-stream')
    async def prepare_twin(payload: TwinInput):
        if not payload.voice_response:
            raise AIOutputInvalid('Voice input required')
        from .voice_stream import voice_response
        return voice_response(lambda:run_twin(payload))

    @app.post('/twin/voice-fast')
    async def fast_twin(payload: TwinInput):
        if not payload.voice_response or not getattr(active_twin,'quote_answers',False):
            raise AIOutputInvalid('Fast voice requires the source-selection adapter')
        from .voice_stream import voice_response
        return voice_response(lambda:run_twin(payload),review_required=False)

    @app.post('/twin/voice-live')
    async def live_twin(payload: TwinInput):
        if not payload.voice_response or not getattr(active_twin,'quote_answers',False):
            raise AIOutputInvalid('Streaming voice requires source selection')
        from .voice_stream import voice_response
        return voice_response(lambda:run_twin(payload),review_required=False,stream_generation=True)

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

    @app.post("/persona", response_model=PersonaOutput)
    async def answer_persona(payload: PersonaInput, request: Request) -> PersonaOutput:
        if payload.voice_response:
            from .cancellation import until_disconnect
            return await until_disconnect(request,lambda: run_persona(payload))
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(run_persona,payload)

    def run_persona(payload):
        if active_persona is None:
            raise ProviderUnavailable("Persona requires the configured Weixin adapter")
        started = monotonic()
        if not slots.acquire(timeout=min(15, active_persona.total_timeout_seconds)):
            if monotonic() - started >= active_persona.total_timeout_seconds:
                raise ProviderTimeout("Persona request budget exhausted waiting for capacity")
            raise ProviderUnavailable("AI Core capacity is busy")
        try:
            chat=getattr(active_persona,'chat',None)
            with (chat.transport_scope(timeout_seconds=settings.voice_call_timeout_seconds,
                  json_retry_after_seconds=settings.effective_voice_json_retry_after_seconds,
                  **({'json_hedged':True} if settings.voice_json_hedged else {}))
                  if payload.voice_response and hasattr(chat,'transport_scope') else nullcontext()):
                return active_persona.answer(payload, started_at=started)
        finally:
            slots.release()

    @app.post('/persona/voice-stream')
    async def prepare_persona(payload: PersonaInput):
        if not payload.voice_response:
            raise AIOutputInvalid('Voice input required')
        from .voice_stream import voice_response
        return voice_response(lambda:run_persona(payload))

    @app.post('/persona/voice-fast')
    async def fast_persona(payload: PersonaInput):
        if not payload.voice_response:
            raise AIOutputInvalid('Voice input required')
        from .voice_stream import voice_response
        return voice_response(lambda:run_persona(payload),review_required=False)

    @app.post('/persona/voice-live')
    async def live_persona(payload: PersonaInput):
        if not payload.voice_response:raise AIOutputInvalid('Voice input required')
        from .voice_stream import voice_response
        return voice_response(lambda:run_persona(payload),review_required=False,stream_generation=True)

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

    @app.post('/narrative-proposals')
    def narrative_proposals(payload:NarrativeInput):
        if active_profile is None:
            raise ProviderUnavailable('Narrative organization requires configured provider')
        if not slots.acquire(blocking=False):
            raise ProviderUnavailable('AI Core capacity is busy')
        try:
            return active_profile.propose_narrative(payload)
        finally:
            slots.release()

    @app.post('/expression')
    def expression(payload: ExpressionInput):
        if active_profile is None or not hasattr(active_profile,'chat'):
            raise ProviderUnavailable('Expression requires configured provider')
        if not slots.acquire(timeout=15): raise ProviderUnavailable('AI Core capacity is busy')
        try:
            return ExpressionProvider(active_profile.chat).express(payload)
        finally:
            slots.release()

    return app

__all__ = ["create_app"]
