from functools import lru_cache
from typing import Literal

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
    stt_backend: Literal["fake"] = "fake"
    ai_backend: Literal["fake", "http"] = "fake"
    ai_core_url: str = "http://127.0.0.1:8100"
    # AI Core's URL path is its own surface, not the contract's: the contract
    # fixes the payload shapes, not the endpoint. Configurable so confirming it
    # with the AI Core owner needs no code change.
    ai_core_path: str = "/process"
    ai_timeout_seconds: float = 30.0

    # One processing stage per worker tick, so a transition is observable from
# outside the process (ADR-0001 D8). The retry budget is per stage: a stage that
# keeps failing ends the Episode as failed, and a stage that succeeds does not
# spend the next stage's attempts.
    job_max_attempts: int = 3
    job_retry_backoff_seconds: int = 5
    job_lease_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings for the ASGI entrypoint and the Alembic env."""
    return Settings()