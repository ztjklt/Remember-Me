from contextlib import contextmanager
import httpx
import pytest
from app.config import Settings
from app.durable_relay_asr import DurableRelaySttProvider
from app.errors import SttFailed, SttTimeout, SttUnavailable
from app.storage.memory import InMemoryObjectStore


class Gate:
    @contextmanager
    def slot(self): yield
    def defer(self, _): pass


def settings(tmp_path):
    return Settings(stt_backend='relay', relay_asr_api_key='fixture-key',
        relay_asr_url='https://ai-router-cn-pub.anker-in.com/chat/completions',
        relay_asr_model='hackathon/v_model/qwen-audio-3.0-asr-flash',
        relay_asr_state_dir=str(tmp_path), relay_asr_checkpoint_backend='object_store')


def test_cold_resume_uses_saved_transcript_and_checks_consent(tmp_path, monkeypatch):
    calls = []; checkpoints = InMemoryObjectStore()
    def post(*_, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, json={'model': 'qwen-asr-actual', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': '我没有决定。'}}]})
    monkeypatch.setattr(httpx, 'post', post)
    def provider(directory):
        return DurableRelaySttProvider(settings(directory), checkpoints, gate=Gate())
    first = provider(tmp_path/'first').transcribe(b'fixture audio', 'audio/wav')
    second = provider(tmp_path/'replacement').transcribe(b'fixture audio', 'audio/wav')
    assert first.text == second.text == '我没有决定。' and len(calls) == 1
    def revoked(): raise SttFailed('fixture consent revoked')
    with pytest.raises(SttFailed):
        provider(tmp_path/'third').transcribe_authorized(b'fixture audio', 'audio/wav', revoked)
    assert len(calls) == 1


def test_uncertain_request_never_replays_after_restart(tmp_path, monkeypatch):
    calls = []; checkpoints = InMemoryObjectStore()
    def post(*_, **kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout('fixture lost acknowledgement')
    monkeypatch.setattr(httpx, 'post', post)
    with pytest.raises(SttTimeout):
        DurableRelaySttProvider(settings(tmp_path/'first'), checkpoints, gate=Gate()).transcribe(b'fixture', 'audio/wav')
    with pytest.raises(SttFailed):
        DurableRelaySttProvider(settings(tmp_path/'second'), checkpoints, gate=Gate()).transcribe(b'fixture', 'audio/wav')
    assert len(calls) == 1


def test_storage_failure_and_auth_rejection_do_not_fabricate_success(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(httpx, 'post', lambda *a, **kw: calls.append(kw) or httpx.Response(401))
    class Broken(InMemoryObjectStore):
        def put(self, *args): raise RuntimeError('fixture unavailable')
    with pytest.raises(SttUnavailable):
        DurableRelaySttProvider(settings(tmp_path/'broken'), Broken(), gate=Gate()).transcribe(b'fixture', 'audio/wav')
    assert calls == []
    checkpoints = InMemoryObjectStore()
    provider = DurableRelaySttProvider(settings(tmp_path/'valid'), checkpoints, gate=Gate())
    with pytest.raises(SttFailed): provider.transcribe(b'fixture', 'audio/wav')
    with pytest.raises(SttFailed): provider.transcribe(b'fixture', 'audio/wav')
    assert len(calls) == 2  # Explicitly rejected requests did not create an uncertain checkpoint.
