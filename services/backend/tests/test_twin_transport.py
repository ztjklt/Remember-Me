import httpx
import pytest
from app.twin_client import TwinClient, TwinUnavailable


@pytest.mark.parametrize('code', ['AI_SCHEMA_INVALID', 'EVIDENCE_INVALID', 'AI_AUTH_FAILED'])
def test_semantic_or_auth_failure_is_not_transient(monkeypatch, code):
    def post(*args, **kwargs):
        return httpx.Response(502, json={'error_code': code}, request=httpx.Request('POST', 'http://ai/twin'))
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(TwinUnavailable) as failure:
        TwinClient('http://ai', 2).answer('问题', [])
    assert getattr(failure.value, 'retryable', True) is False
    assert failure.value.code == code


def test_capacity_error_remains_transient(monkeypatch):
    def post(*args, **kwargs):
        return httpx.Response(503, json={'error_code': 'AI_UNAVAILABLE'}, request=httpx.Request('POST', 'http://ai/twin'))
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(TwinUnavailable) as failure:
        TwinClient('http://ai', 2).answer('问题', [])
    assert getattr(failure.value, 'retryable', True) is True
