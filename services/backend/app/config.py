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
    # PostgreSQL DSN once the deployment configuration lands (see ADR-0001 D3).
    database_url: str = "sqlite:///./var/remember-me.db"

    # Deployment uses S3-compatible object storage. That adapter and its
    # settings arrive with Issue #1, which owns the audio object path.
    object_store_backend: Literal["local", "memory"] = "local"
    object_store_root: str = "./var/object-store"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings for the ASGI entrypoint and the Alembic env."""
    return Settings()