"""Exercise the real STT wire and lazy optional-engine boundary without weights."""

from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
import sys

import pytest
from fastapi.testclient import TestClient

from app import local_stt
from app.faster_stt import FasterWhisperEngine, LocalSttError


@pytest.fixture(autouse=True)
def clear_engine():
    local_stt._engine.cache_clear()
    yield
    local_stt._engine.cache_clear()


def test_http_wire_preserves_text_and_version(monkeypatch):
    expected = {"text": "以前喜欢热闹，现在不喜欢。", "model_version": "weights@123"}
    def recognize(audio):
        assert audio == b"recorded audio"
        return expected
    monkeypatch.setattr(local_stt, "_engine", lambda: recognize)
    with TestClient(local_stt.app) as client:
        response = client.post("/transcribe", content=b"recorded audio",
                               headers={"Content-Type": "audio/mp4; codecs=mp4a"})
    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize("body,mime,status", [
    (b"audio", "application/json", 415), (b"", "audio/wav", 422),
    (b"12345", "audio/wav", 413),
])
def test_invalid_inputs_never_reach_model(monkeypatch, body, mime, status):
    monkeypatch.setattr(local_stt, "MAX_AUDIO_BYTES", 4)
    def unexpected():
        pytest.fail("Invalid input reached the model")
    monkeypatch.setattr(local_stt, "_engine", unexpected)
    with TestClient(local_stt.app) as client:
        assert client.post("/transcribe", content=body,
                           headers={"Content-Type": mime}).status_code == status
    assert not local_stt._inference_slot.locked()


def test_busy_engine_returns_retryable_status_and_keeps_health_available(monkeypatch):
    entered, release = Event(), Event()
    def slow(audio):
        entered.set()
        assert release.wait(5)
        return {"text": "你好", "model_version": "test"}
    monkeypatch.setattr(local_stt, "_engine", lambda: slow)
    with TestClient(local_stt.app) as client:
        results = []
        task = Thread(target=lambda: results.append(client.post(
            "/transcribe", content=b"audio", headers={"Content-Type": "audio/wav"})))
        task.start()
        try:
            assert entered.wait(5)
            response = client.post("/transcribe", content=b"audio",
                                   headers={"Content-Type": "audio/wav"})
            assert response.status_code == 503
            assert response.headers["Retry-After"] == "1"
            assert client.get("/health").status_code == 200
        finally:
            release.set()
            task.join(5)
        assert results[0].status_code == 200


def test_model_errors_release_slot_without_exposing_internal_details(monkeypatch):
    def fail(audio):
        raise RuntimeError("private transcript and /private/model/path")
    monkeypatch.setattr(local_stt, "_engine", lambda: fail)
    with TestClient(local_stt.app) as client:
        response = client.post("/transcribe", content=b"audio",
                               headers={"Content-Type": "audio/wav"})
    assert response.status_code == 503
    assert "private" not in response.text
    assert not local_stt._inference_slot.locked()


def test_timeout_is_retryable_504(monkeypatch):
    def fail(audio):
        raise LocalSttError("Local transcription timed out", 504)
    monkeypatch.setattr(local_stt, "_engine", lambda: fail)
    with TestClient(local_stt.app) as client:
        assert client.post("/transcribe", content=b"audio",
                           headers={"Content-Type": "audio/wav"}).status_code == 504


def test_engine_selection_preserves_cpp_default_and_never_silently_falls_back(monkeypatch):
    monkeypatch.delenv("REMEMBER_LOCAL_STT_ENGINE", raising=False)
    assert local_stt._engine() is local_stt.transcribe_audio
    local_stt._engine.cache_clear()
    monkeypatch.setenv("REMEMBER_LOCAL_STT_ENGINE", "faster_whisper")
    monkeypatch.delenv("REMEMBER_FASTER_WHISPER_MODEL_PATH", raising=False)
    with pytest.raises(LocalSttError, match="MODEL_PATH"):
        local_stt._engine()


def test_faster_engine_consumes_lazy_segments_once_and_fingerprints_weights(monkeypatch, tmp_path):
    import app.faster_stt as engine_module
    (tmp_path / "model.bin").write_bytes(b"weights-v1")
    (tmp_path / "config.json").write_text("{}")
    calls = []
    class Model:
        model = SimpleNamespace(is_multilingual=True)
        def __init__(self, path, **options):
            assert Path(path) == tmp_path
            assert options["local_files_only"] is True
            calls.append("loaded")
        def transcribe(self, audio, **options):
            assert audio.read() == b"audio"
            assert options["vad_filter"] is True
            assert options["language"] == "zh"
            def segments():
                yield SimpleNamespace(text="我不喜欢")
                yield SimpleNamespace(text="热闹。")
            return segments(), None
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, "av.error", SimpleNamespace(FFmpegError=type("DecodeError", (Exception,), {})))
    monkeypatch.setattr(engine_module, "version", lambda name: "test-library")
    first = FasterWhisperEngine(tmp_path)
    result = first.transcribe(b"audio")
    assert result["text"] == "我不喜欢热闹。"
    assert len(result["model_version"]) <= 64
    assert first.transcribe(b"audio") == result
    assert calls == ["loaded"]
    (tmp_path / "model.bin").write_bytes(b"weights-v2")
    assert FasterWhisperEngine(tmp_path).transcribe(b"audio")["model_version"] != result["model_version"]


def test_faster_engine_rejects_missing_local_weights(tmp_path):
    with pytest.raises(LocalSttError, match="directory"):
        FasterWhisperEngine(tmp_path).transcribe(b"audio")
