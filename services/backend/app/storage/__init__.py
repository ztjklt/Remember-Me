"""Object storage boundary.

Raw audio and other assets live in object storage; the database stores only a
reference plus object metadata, never the bytes (ADR-0001 D5). Three backends sit
behind the one `ObjectStore` protocol: the local filesystem for development, an
in-memory store for tests, and S3-compatible storage for deployment.
"""

from .base import ObjectStore, StoredObject, checksum_of, validate_key
from .local import LocalObjectStore
from .memory import InMemoryObjectStore
from .s3 import S3ObjectStore
from ..config import Settings

__all__ = [
    "InMemoryObjectStore",
    "LocalObjectStore",
    "ObjectStore",
    "S3ObjectStore",
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
    if settings.object_store_backend == "s3":
        return S3ObjectStore(
            settings.object_store_bucket,
            endpoint_url=settings.object_store_endpoint_url,
            region=settings.object_store_region,
        )
    raise ValueError(
        f"Unsupported object store backend: {settings.object_store_backend!r}"
    )