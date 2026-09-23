import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

_ALLOWED_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,1023}$")


@dataclass(frozen=True)
class StoredObject:
    """Metadata describing one stored object. The bytes stay in object storage."""

    key: str
    size_bytes: int
    content_type: str
    checksum: str


class ObjectStore(Protocol):
    """Boundary every object storage provider sits behind."""

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def healthcheck(self) -> None: ...


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_key(key: str) -> str:
    """Reject keys that could escape a store's root or span outside its namespace."""
    if not _ALLOWED_KEY.match(key) or ".." in key or "//" in key or key.endswith("/"):
        raise ValueError(f"Invalid object key: {key!r}")
    return key