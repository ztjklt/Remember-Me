import pytest

from app.storage import InMemoryObjectStore, LocalObjectStore, validate_key
from app.storage.base import checksum_of

KEY = "audio/episode_1/original"
PAYLOAD = b"raw audio bytes"


@pytest.fixture(params=["local", "memory"])
def store(request, tmp_path):
    if request.param == "local":
        return LocalObjectStore(tmp_path / "objects")
    return InMemoryObjectStore()


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