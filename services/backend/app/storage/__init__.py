"""Object storage boundary.

Raw audio and other assets live in object storage; the database stores only a
reference plus object metadata, never the bytes (ADR-0001 D5). Issue #8 ships the
local filesystem and in-memory implementations; the S3-compatible deployment
adapter arrives with Issue #1, which owns the audio object path.
"""

from .base import ObjectStore, StoredObject, checksum_of, validate_key
from .local import LocalObjectStore
from .memory import InMemoryObjectStore
from ..config import Settings

__all__ = [
    "InMemoryObjectStore",
    "LocalObjectStore",
    "ObjectStore",
    "StoredObject",
    "build_object_store",
    "checksum_of",
    "validate_key",
]


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store_backend == "local":
        return LocalObjectStore(settings.object_store_root)
    if settings.object_store_backend == "memory":
        return InMemoryObjectStore()
    raise ValueError(
        f"Unsupported object store backend: {settings.object_store_backend!r}"
    )