from pathlib import Path

from .base import StoredObject, checksum_of, validate_key

_PROBE_KEY = "healthcheck/probe"


class LocalObjectStore:
    """Development and test object store backed by the local filesystem.

    The root directory is created lazily so that importing the application has no
    filesystem side effect.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Object key escapes the store root: {key!r}")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            checksum=checksum_of(data),
        )

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def healthcheck(self) -> None:
        """Prove the root is writable and readable, then clean up after itself."""
        self.put(_PROBE_KEY, b"probe", "application/octet-stream")
        try:
            if self.get(_PROBE_KEY) != b"probe":
                raise RuntimeError(f"Object store at {self.root} did not return what it stored")
        finally:
            probe_path = self._path(_PROBE_KEY)
            self.delete(_PROBE_KEY)
            probe_dir = probe_path.parent
            if probe_dir != self.root:
                try:
                    # rmdir refuses to remove a non-empty directory, so a stored
                    # object can never be deleted by this cleanup.
                    probe_dir.rmdir()
                except OSError:
                    pass