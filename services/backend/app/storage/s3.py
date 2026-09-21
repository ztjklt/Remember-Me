"""S3-compatible object storage: the deployment adapter for raw audio.

One adapter serves AWS S3, MinIO, and any other S3-compatible service, because
the only thing that differs is the endpoint and whether path-style addressing is
required. A custom endpoint means path-style: the virtual-host form assumes DNS
records like `bucket.example.com`, which a local MinIO or an on-premise
compatible service usually does not have.

The client is built lazily so that importing the application has no network side
effect and no credential lookup, matching the local store's lazy root creation.
"""

from typing import Any

from botocore.config import Config
from botocore.exceptions import ClientError

from .base import StoredObject, checksum_of, validate_key

_PROBE_KEY = "healthcheck/probe"
_MISSING = {"404", "NoSuchKey", "NotFound"}


class S3ObjectStore:
    """Object store backed by an S3-compatible service."""

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str | None = None,
    ) -> None:
        if not bucket:
            raise ValueError("An S3 bucket name is required")
        self.bucket = bucket
        self.endpoint_url = endpoint_url or None
        self.region = region or None
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        import boto3

        config = Config(
            # A retried upload is the client's decision, not a silent one here:
            # one attempt per call keeps the failure the worker sees attributable,
            # and the job's own retry/backoff is what handles a transient outage.
            retries={"max_attempts": 1},
            # Explicit, so the address form does not depend on which endpoint
            # happens to be configured.
            s3={"addressing_style": "path" if self.endpoint_url else "auto"},
        )
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region,
            config=config,
        )

    def put(self, key: str, data: bytes, content_type: str) -> StoredObject:
        validate_key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        # Our own digest rather than the service's ETag: an ETag is an MD5 for a
        # simple upload but not for a multipart one, so it cannot be compared
        # across upload paths or against a client-supplied checksum.
        return StoredObject(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            checksum=checksum_of(data),
        )

    def get(self, key: str) -> bytes:
        validate_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if _error_code(error) in _MISSING:
                raise FileNotFoundError(f"No object stored at {key!r}") from error
            raise
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        validate_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if _error_code(error) in _MISSING:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        validate_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def healthcheck(self) -> None:
        """Prove the bucket accepts a write, returns it, and accepts a delete.

        A bucket that exists but is not writable would otherwise look healthy
        until the first upload failed.
        """
        self.put(_PROBE_KEY, b"probe", "application/octet-stream")
        try:
            if self.get(_PROBE_KEY) != b"probe":
                raise RuntimeError(
                    f"Object store bucket {self.bucket!r} did not return what it stored"
                )
        finally:
            self.delete(_PROBE_KEY)


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))