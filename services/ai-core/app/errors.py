"""Stable internal errors for the AI Core boundary."""

from __future__ import annotations

from typing import ClassVar


class AICoreError(Exception):
    code: ClassVar[str] = "AI_CORE_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AIOutputInvalid(AICoreError):
    code = "AI_SCHEMA_INVALID"


class EvidenceInvalid(AICoreError):
    code = "EVIDENCE_INVALID"


class ProviderUnavailable(AICoreError):
    code = "AI_UNAVAILABLE"


class ProviderRateLimited(ProviderUnavailable):
    """Same public error contract; callers must not immediately retry HTTP 429."""

    def __init__(self, retry_after_seconds: float = 60):
        super().__init__('Provider rate limited; try again after the cooldown')
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeout(AICoreError):
    code = "AI_TIMEOUT"


__all__ = [
    "AICoreError",
    "AIOutputInvalid",
    "EvidenceInvalid",
    "ProviderUnavailable",
    "ProviderTimeout",
]

class ProviderAuthenticationFailed(AICoreError):
    code = "AI_AUTH_FAILED"
