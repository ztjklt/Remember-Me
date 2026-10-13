"""Every object store backend, against the same contract.

The three backends are interchangeable, so the round trip and the healthcheck are
parametrized over all of them: an adapter that only satisfied the two in-process
stores would be a deployment backend nothing had ever written to. The S3 tests
run in-process through moto, so the deployment path is exercised without a
server, and the service-specific quirks that are easy to get wrong — a missing
object versus a missing bucket, an ETag versus a checksum — are pinned here.
"""

import hashlib
import os

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.storage import (
    InMemoryObjectStore,
    LocalObjectStore,
    S3ObjectStore,
    validate_key,
)
from app.storage.base import checksum_of

KEY = "audio/episode_1/original"
PAYLOAD = b"raw audio bytes"
BUCKET = "remember-me-audio"
REGION = "us-east-1"


def s3_store(*, endpoint_url: str | None = None, create_bucket: bool = True):
    """A store pointed at moto, with its bucket created unless a test says not."""
    if create_bucket:
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
    return S3ObjectStore(
        BUCKET, endpoint_url=endpoint_url, region=REGION
    )


@pytest.fixture(params=["local", "memory", "s3"])
def store(request, tmp_path):
    if request.param == "s3":
        with mock_aws():
            yield s3_store()
        return
    if request.param == "local":
        yield LocalObjectStore(tmp_path / "objects")
        return
    yield InMemoryObjectStore()


def test_put_get_exists_delete_round_trip(store):
    stored = store.put(KEY, PAYLOAD, "audio/wav")

    assert stored.key == KEY
    assert stored.size_bytes == len(PAYLOAD)
    assert stored.checksum == checksum_of(PAYLOAD)
    assert stored.content_type == "audio/wav"
    assert store.exists(KEY) is True
    assert store.get(KEY) == PAYLOAD

    store.delete(KEY)

    assert store.exists(KEY) is False
    with pytest.raises(FileNotFoundError):
        store.get(KEY)


def test_healthcheck_passes(store):
    store.healthcheck()


def test_the_local_store_creates_nested_directories(tmp_path):
    root = tmp_path / "objects"
    store = LocalObjectStore(root)

    store.put(KEY, PAYLOAD, "audio/wav")

    assert (root / KEY).read_bytes() == PAYLOAD
    # Windows does not expose ACLs through POSIX mode bits. File round-trip
    # remains tested on both systems; POSIX permission checks run on POSIX.
    if os.name != 'nt':
        assert ((root / KEY).stat().st_mode & 0o777) == 0o600
        assert ((root / KEY).parent.stat().st_mode & 0o777) == 0o700


def test_the_local_store_leaves_no_probe_behind(tmp_path):
    root = tmp_path / "objects"
    store = LocalObjectStore(root)

    store.healthcheck()

    assert list(root.rglob("*")) == []


def test_constructing_the_local_store_writes_nothing(tmp_path):
    root = tmp_path / "objects"

    LocalObjectStore(root)

    assert not root.exists()


def test_the_local_store_refuses_a_key_that_escapes_the_root(tmp_path):
    root = tmp_path / "objects"
    store = LocalObjectStore(root)

    with pytest.raises(ValueError):
        store.put("../outside.txt", PAYLOAD, "audio/wav")

    assert not (tmp_path / "outside.txt").exists()


@pytest.mark.parametrize(
    "key",
    [
        "",
        "/absolute/path",
        "../escape",
        "audio/../../escape",
        "audio//original",
        "trailing/",
        "with space",
        "with?query",
    ],
)
def test_validate_key_rejects_unsafe_keys(key):
    with pytest.raises(ValueError):
        validate_key(key)


@pytest.mark.parametrize("key", ["a", "audio/episode_1/original", "a.b_c-d/e.part"])
def test_validate_key_accepts_normal_keys(key):
    assert validate_key(key) == key


def test_the_s3_store_needs_a_bucket_name():
    """A store with no bucket would fail on the first upload instead of at start."""
    with pytest.raises(ValueError, match="bucket"):
        S3ObjectStore("")


def test_the_s3_store_reports_a_missing_object_as_missing():
    """The worker reads FileNotFoundError as "the audio is not there"; a bucket
    that is gone is not that, and the two must not be conflated."""
    with mock_aws():
        store = s3_store()

        assert store.exists(KEY) is False
        with pytest.raises(FileNotFoundError):
            store.get(KEY)


def test_a_missing_bucket_is_not_reported_as_a_missing_object():
    with mock_aws():
        store = s3_store(create_bucket=False)

        # Not FileNotFoundError: this is infrastructure, and mapping it to a
        # missing recording would send whoever reads the Episode after the wrong
        # problem.
        with pytest.raises(ClientError):
            store.get(KEY)


def test_the_s3_store_keeps_the_content_type_and_our_own_checksum():
    with mock_aws():
        store = s3_store()

        stored = store.put(KEY, PAYLOAD, "audio/wav")
        head = store.client.head_object(Bucket=BUCKET, Key=KEY)

        assert head["ContentType"] == "audio/wav"
        assert head["ContentLength"] == len(PAYLOAD)
        assert stored.checksum == checksum_of(PAYLOAD)
        # The service's ETag is an MD5, ours is a SHA-256: keeping our own digest
        # is what makes it comparable against a client-supplied one and across
        # upload paths.
        assert stored.checksum != head["ETag"].strip('"')
        assert hashlib.md5(PAYLOAD).hexdigest() == head["ETag"].strip('"')


def test_the_s3_healthcheck_leaves_no_probe_behind():
    with mock_aws():
        store = s3_store()

        store.healthcheck()

        assert store.exists("healthcheck/probe") is False
        assert store.client.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0


def test_a_custom_endpoint_switches_to_path_style_addressing():
    """A local MinIO or an on-premise service has no bucket.<host> DNS record."""
    with mock_aws():
        custom = s3_store(endpoint_url="http://minio.internal:9000")
        aws = s3_store()

        assert custom.client.meta.config.s3["addressing_style"] == "path"
        assert aws.client.meta.config.s3["addressing_style"] == "auto"


def test_the_s3_client_does_no_work_until_it_is_used():
    """Importing or constructing the store must not look for credentials."""
    store = S3ObjectStore(BUCKET, region=REGION)

    assert store._client is None


def test_the_s3_store_refuses_a_key_that_escapes_the_namespace():
    with mock_aws():
        store = s3_store()

        with pytest.raises(ValueError):
            store.put("../outside", PAYLOAD, "audio/wav")

        assert store.client.list_objects_v2(Bucket=BUCKET)["KeyCount"] == 0
