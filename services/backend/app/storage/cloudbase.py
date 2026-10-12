"""PG Storage HTTP adapter. Only the backend holds the service credential."""
import re
import uuid
from urllib.parse import quote

import httpx

from .base import StoredObject, checksum_of, validate_key


class CloudBaseObjectStore:
    def __init__(self, environment_id: str, bucket: str, api_key: str):
        if not re.fullmatch(r"[a-z0-9-]+", environment_id):
            raise ValueError("Invalid CloudBase environment ID")
        if not re.fullmatch(r"remember-me-ios-[a-z0-9-]+", bucket) or not api_key.strip():
            raise ValueError("An independent private bucket and server credential are required")
        self.origin = f"https://{environment_id}.api.tcloudbasegateway.com"
        self.bucket = bucket
        self._api_key = api_key

    def _request(self, method, key, **kwargs):
        key = validate_key(key)
        path = f"/v1/storages/object/{quote(self.bucket, safe='')}/{quote(key, safe='/')}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        headers.update(kwargs.pop("headers", {}))
        # Never forward a service credential or original recording to a redirect.
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.request(method, self.origin + path, headers=headers, **kwargs)
        return response

    @staticmethod
    def _check(response):
        if not 200 <= response.status_code < 300:
            # Do not include response bodies, which may contain private object metadata.
            raise RuntimeError(f"CloudBase storage request failed (HTTP {response.status_code})")

    def put(self, key, data, content_type):
        response = self._request("POST", key, content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"})
        self._check(response)
        return StoredObject(key, len(data), content_type, checksum_of(data))

    def get(self, key):
        response = self._request("GET", key)
        if response.status_code == 404:
            raise FileNotFoundError("CloudBase object not found")
        self._check(response)
        return response.content

    def exists(self, key):
        response = self._request("HEAD", key)
        if response.status_code == 404:
            return False
        self._check(response)
        return True

    def delete(self, key):
        response = self._request("DELETE", key)
        if response.status_code != 404:
            self._check(response)

    def healthcheck(self):
        key = f"healthcheck/{uuid.uuid4().hex}"
        self.put(key, b"probe", "application/octet-stream")
        try:
            if self.get(key) != b"probe":
                raise RuntimeError("CloudBase object store probe mismatch")
        finally:
            self.delete(key)
