from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration read from the environment or a local .env file.

    Every key uses the REMEMBER_ prefix. No secret is committed; .env.example
    documents the expected keys.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REMEMBER_",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "staging", "test"] = "development"
    log_level: str = "INFO"

    # SQLite is the local development and test default. Deployment supplies a
    # PostgreSQL DSN and adds the driver (see ADR-0001 D3).
    database_url: str = "sqlite:///./var/remember-me.db"

    # Deployment uses S3-compatible object storage; local and memory serve
    # development, CI, and tests (ADR-0001 D5).
    object_store_backend: Literal["local", "memory", "s3"] = "local"
    object_store_root: str = "./var/object-store"
    object_store_bucket: str = "remember-me-audio"
    # Set this for an S3-compatible service that is not AWS itself (MinIO and
    # friends). Left unset, boto3 resolves the AWS endpoint for the region.
    object_store_endpoint_url: str | None = None
    object_store_region: str = "us-east-1"

    # The upload boundary refuses anything larger. The client also enforces a
    # limit, but a server-side limit is the one that cannot be bypassed.
    max_upload_bytes: int = 25 * 1024 * 1024

    # Providers are not frozen, so both of these name an adapter rather than a
    # vendor (ADR-0001 D9). "fake" is a deterministic local implementation.
    stt_backend: Literal["fake", "http", "dashscope"] = "fake"
    stt_url: str = "http://127.0.0.1:8200"
    stt_path: str = "/transcribe"
    # Transcription is slower than inference per byte of input, so this budget is
    # larger than AI Core's. A timeout is a failure the retry budget handles.
    stt_timeout_seconds: float = 60.0
    stt_model: str = ""
    stt_api_key: SecretStr = SecretStr("")
    ai_backend: Literal["fake", "http"] = "fake"
    ai_core_url: str = "http://127.0.0.1:8100"
    # AI Core's URL path is its own surface, not the contract's: the contract
    # fixes the payload shapes, not the endpoint. Configurable so confirming it
    # with the AI Core owner needs no code change.
    ai_core_path: str = "/process"
    agent_enabled: bool = False
    agent_timeout_seconds: float = 45.0
    ai_timeout_seconds: float = 30.0

    # A placeholder provider is refused outside development and test. This is the
    # explicit way to say "yes, here too" — bringing an environment up end to end
    # before its real provider exists (app/providers.py). Building a fake because
    # of it logs a warning, so the decision is visible at startup.
    allow_fake_providers: bool = False

    # One processing stage per worker tick, so a transition is observable from
    # outside the process (ADR-0001 D8). The retry budget is per stage: a stage
    # that keeps failing ends the Episode as failed, and a stage that succeeds
    # does not spend the next stage's attempts.
    job_max_attempts: int = 3
    job_retry_backoff_seconds: int = 5
    # How long a claim is good for, and how long a stage may run before the claim
    # has to be renewed (app/worker.py). A lease that expires returns the work to
    # any worker, and a result is committed only while the claim is held.
    job_lease_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings for the ASGI entrypoint and the Alembic env."""
    return Settings()
