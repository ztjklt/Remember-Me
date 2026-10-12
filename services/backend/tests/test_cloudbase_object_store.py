import httpx
import pytest
from app.storage.cloudbase import CloudBaseObjectStore


def store(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))
    return CloudBaseObjectStore('fixture-ios', 'remember-me-ios-audio', 'fixture-server-key')


def test_readiness_roundtrip_and_checkpoint_overwrite(monkeypatch):
    objects = {}
    def remote(request):
        assert request.headers['authorization'] == 'Bearer fixture-server-key'
        assert request.url.host == 'fixture-ios.api.tcloudbasegateway.com'
        key = request.url.path
        if request.method == 'POST':
            assert request.headers['x-upsert'] == 'true'
            objects[key] = request.content
        elif request.method == 'DELETE':
            objects.pop(key, None)
        elif key not in objects:
            return httpx.Response(404)
        return httpx.Response(200, content=objects.get(key, b''))
    adapter = store(monkeypatch, remote)
    adapter.healthcheck()
    assert objects == {}
    assert not adapter.exists('missing')
    adapter.put('asr-checkpoints/fixture.json', b'first', 'application/json')
    adapter.put('asr-checkpoints/fixture.json', b'second', 'application/json')
    assert adapter.get('asr-checkpoints/fixture.json') == b'second'
    assert adapter.exists('asr-checkpoints/fixture.json')


def test_outage_is_not_missing_and_redirect_never_exports(monkeypatch):
    requests = []
    def remote(request):
        requests.append(request)
        return httpx.Response(302, headers={'Location': 'https://other.invalid/audio'},
            text='fixture private metadata')
    adapter = store(monkeypatch, remote)
    with pytest.raises(RuntimeError, match='HTTP 302') as error:
        adapter.put('original/fixture.m4a', b'fixture audio', 'audio/mp4')
    assert 'private metadata' not in str(error.value)
    assert len(requests) == 1
    with pytest.raises(RuntimeError):
        adapter.get('asr-checkpoints/fixture.json')
    with pytest.raises(ValueError):
        adapter.get('../escape')


def test_not_found_and_idempotent_delete(monkeypatch):
    adapter = store(monkeypatch, lambda _: httpx.Response(404))
    with pytest.raises(FileNotFoundError):
        adapter.get('missing')
    adapter.delete('missing')
