"""Environment-backed settings for the AI Core service."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .prompts import PROMPT_VERSION, SCHEMA_VERSION
from .providers.fixture import FixtureProvider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices(
            "REMEMBER_ENVIRONMENT",
            "AI_ENVIRONMENT",
            "ENVIRONMENT",
        ),
    )
    provider: Literal["fixture", "openai_compatible", "ollama", "deepseek"] = Field(
        default="fixture",
        validation_alias="AI_PROVIDER",
    )
    model: str = Field(default=FixtureProvider.default_model_version, validation_alias="AI_MODEL")
    base_url: str = Field(
        default="http://127.0.0.1:8000/v1",
        validation_alias="AI_BASE_URL",
    )
    api_key: SecretStr = Field(default=SecretStr(""), validation_alias="AI_API_KEY")
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        allow_inf_nan=False,
        validation_alias="AI_TIMEOUT_SECONDS",
    )
    model_version: str = Field(
        default=FixtureProvider.default_model_version,
        min_length=1,
        validation_alias="AI_MODEL_VERSION",
    )
    prompt_version: str = Field(
        default=PROMPT_VERSION,
        min_length=1,
        validation_alias="AI_PROMPT_VERSION",
    )
    schema_version: str = Field(
        default=SCHEMA_VERSION,
        min_length=1,
        validation_alias="AI_SCHEMA_VERSION",
    )
    max_concurrent_requests: int = Field(default=4, ge=1, validation_alias="AI_MAX_CONCURRENT_REQUESTS")
    max_request_bytes: int = Field(default=1_048_576, ge=1, validation_alias="AI_MAX_REQUEST_BYTES")
    max_response_bytes: int = Field(default=1_048_576, ge=1, validation_alias="AI_MAX_RESPONSE_BYTES")

    @field_validator("model", "model_version", "prompt_version", "schema_version")
    @classmethod
    def non_blank_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model and version names must not be blank")
        return value

    @field_validator("base_url")
    @classmethod
    def valid_provider_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
                and not parsed.password and not parsed.query and not parsed.fragment
                and not any(char.isspace() for char in value)
            )
            _ = parsed.port  # Also reject malformed ports before the first request.
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("AI_BASE_URL must be an HTTP(S) URL without credentials, query or fragment")
        return value

    @model_validator(mode="after")
    def real_provider_has_explicit_identity(self) -> "Settings":
        if self.prompt_version != PROMPT_VERSION or self.schema_version != SCHEMA_VERSION:
            raise ValueError("prompt/schema versions must identify the implementation in this build")
        if self.provider == "openai_compatible" and (
            self.model.startswith("fixture-ai-") or self.model_version.startswith("fixture-ai-")
        ):
            raise ValueError("real providers require explicit AI_MODEL and AI_MODEL_VERSION")
        if self.provider == "ollama":
            if self.model.startswith("fixture-ai-"):
                raise ValueError("Ollama requires an explicit installed AI_MODEL")
            parsed = urlsplit(self.base_url)
            if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path not in {"", "/"}:
                raise ValueError("Ollama must listen on this Mac's loopback address")
        if self.provider == "deepseek":
            parsed = urlsplit(self.base_url)
            if (parsed.scheme != "https" or parsed.hostname != "api.deepseek.com"
                    or parsed.path not in {"", "/"} or parsed.port is not None):
                raise ValueError("DeepSeek credentials may only be sent to https://api.deepseek.com")
            if self.model not in {"deepseek-v4-flash", "deepseek-flash"}:
                raise ValueError("DeepSeek Flash requires its official model name")
            if not self.api_key.get_secret_value().strip():
                raise ValueError("DeepSeek requires AI_API_KEY")
        return self


__all__ = ["Settings"]
