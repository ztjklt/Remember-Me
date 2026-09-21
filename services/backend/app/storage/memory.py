from .base import StoredObject, checksum_of, validate_key


class InMemoryObjectStore:
    """Object store for tests and for a single-process local run."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        validate_key(key)
        self._objects[key] = (data, content_type)
        return StoredObject(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            checksum=checksum_of(data),
        )

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            return self._objects[key][0]
        except KeyError:
            raise FileNotFoundError(f"No object stored at {key!r}") from None

    def exists(self, key: str) -> bool:
        validate_key(key)
        return key in self._objects

    def delete(self, key: str) -> None:
        validate_key(key)
        self._objects.pop(key, None)

    def healthcheck(self) -> None:
        return None