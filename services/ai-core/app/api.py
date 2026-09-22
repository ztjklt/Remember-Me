"""Thin HTTP transport for the provider-neutral AI Core."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import Settings
from .contracts import AICoreInput, AICoreOutput
from .errors import AIOutputInvalid, EvidenceInvalid, ProviderTimeout, ProviderUnavailable
from .extractor import MemoryExtractor
from .providers.fixture import FixtureProvider
from .providers.openai_compatible import OpenAICompatibleProvider


def _build_extractor(settings: Settings) -> MemoryExtractor:
    if settings.provider == "fixture":
        if settings.environment not in {"development", "test"}:
            raise ValueError("fixture provider is allowed only in development and test")
        provider = FixtureProvider()
    else:
        provider = OpenAICompatibleProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout_seconds=settings.timeout_seconds,
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
) -> FastAPI:
    settings = settings or Settings()
    active_extractor = extractor or _build_extractor(settings)
    app = FastAPI(title="Remember Me AI Core", version="0.1.0")

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
    async def process(payload: AICoreInput) -> AICoreOutput:
        return active_extractor.process(payload)

    return app


__all__ = ["create_app"]
