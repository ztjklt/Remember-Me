"""Environment-backed settings for the AI Core service."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .prompts import PROMPT_VERSION, SCHEMA_VERSION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
        populate_by_name=True,
    )

    environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices(
            "REMEMBER_ENVIRONMENT",
            "AI_ENVIRONMENT",
            "ENVIRONMENT",
        ),
    )
    provider: Literal["fixture", "openai_compatible"] = Field(
        default="fixture",
        validation_alias="AI_PROVIDER",
    )
    model: str = Field(default="fixture-ai-v1", validation_alias="AI_MODEL")
    base_url: str = Field(
        default="http://127.0.0.1:8000/v1",
        validation_alias="AI_BASE_URL",
    )
    api_key: str = Field(default="", validation_alias="AI_API_KEY")
    timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        validation_alias="AI_TIMEOUT_SECONDS",
    )
    model_version: str = Field(
        default="fixture-ai-v1",
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


__all__ = ["Settings"]
