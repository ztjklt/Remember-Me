"""Voice QA runs without loading MLX/Qwen or handling anyone's voice."""

import math
import io
import wave
from array import array
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_quality import assess_pcm16
import local_voice


def signal(seconds=6, amplitude=1000, rate=24000):
    return [int(amplitude * math.sin(index * 0.04)) for index in range(int(rate * seconds))]


def test_normal_level_audio_passes_without_claiming_speaker_identity():
    quality = assess_pcm16(signal(), 24000)
    assert quality.duration_seconds == 6
    assert quality.audible_seconds >= 5.9
    assert quality.clipping_ratio == 0


@pytest.mark.parametrize("samples", [[0] * 144000, [32767] * 144000,
    signal(seconds=1) + [0] * 120000, signal(seconds=3)])
def test_silence_clipping_and_short_usable_audio_are_rejected(samples):
    with pytest.raises(ValueError):
        assess_pcm16(samples, 24000)


def test_sample_size_is_rejected_before_decoder_or_model(monkeypatch):
    monkeypatch.setattr(local_voice, "MAX_SAMPLE_BYTES", 4)
    def unexpected(*args):
        pytest.fail("Oversized sample reached decoding")
    monkeypatch.setattr(local_voice, "_sample_wav", unexpected)
    with TestClient(local_voice.app) as client:
        assert client.post("/validate", content=b"12345").status_code == 422


def test_http_validation_decodes_synthetic_wav_without_loading_voice_model(monkeypatch):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(array("h", signal()).tobytes())
    def unexpected():
        pytest.fail("Numerical QA must not load the voice model")
    monkeypatch.setattr(local_voice, "_model", unexpected)
    with TestClient(local_voice.app) as client:
        response = client.post("/validate", content=out.getvalue())
    assert response.status_code == 200, response.text
    assert response.json()["duration_seconds"] == 6
