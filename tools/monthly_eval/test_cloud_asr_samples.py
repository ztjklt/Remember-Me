import hashlib
import json
import pytest
import cloud_asr_samples as cloud


def test_loads_immutable_audio_not_script_and_preserves_simulated_date(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud, 'OUT', tmp_path)
    folder = tmp_path / 'person'; folder.mkdir()
    (folder / 'versioned.wav').write_bytes(b'actual-audio')
    (folder / 'person-01.json').write_text(json.dumps({'audio_file': 'versioned.wav',
        'audio_sha256': hashlib.sha256(b'actual-audio').hexdigest()}))
    person = {'id': 'person', 'episodes': [{'id': 'person-01',
        'simulated_recorded_at': '2026-09-01T10:00:00+08:00', 'script': 'must-not-read.txt'}]}
    date, path, raw, _ = cloud.load_sample(person)
    assert date == '2026-09-01T10:00:00+08:00' and path.name == 'versioned.wav'
    assert raw == b'actual-audio'
    path.write_bytes(b'altered')
    with pytest.raises(RuntimeError, match='hash mismatch'): cloud.load_sample(person)


def test_technical_review_sends_only_asr_draft(monkeypatch, tmp_path):
    calls = []
    def request(method, path, owner, **kwargs):
        calls.append((method, path, kwargs))
        if method == 'PATCH': return {}
        if path.endswith('/transcript-review'): return {'state': 'reviewing', 'transcript': '听到的ASR，不是原稿'}
        return {'status': 'ready' if any(c[0] == 'PATCH' for c in calls) else 'transcribing'}
    monkeypatch.setattr(cloud.product, 'call', request)
    monkeypatch.setattr(cloud.time, 'sleep', lambda _: None)
    row = {}
    cloud.wait_for_review({}, 'ep_real', tmp_path / 'asr.json', row, lambda: None)
    patches = [c for c in calls if c[0] == 'PATCH']
    assert patches[0][2]['json'] == {'transcript': '听到的ASR，不是原稿'}
    assert row['human_listening'] is False


def test_failed_asr_does_not_unlock_extraction_or_retry(monkeypatch, tmp_path):
    calls = []
    def request(method, *args, **kwargs):
        calls.append(method)
        return {'status': 'failed', 'error_code': 'STT_FAILED'}
    monkeypatch.setattr(cloud.product, 'call', request)
    with pytest.raises(RuntimeError, match='STT_FAILED'):
        cloud.wait_for_review({}, 'ep_real', tmp_path / 'asr.json', {}, lambda: None)
    assert calls == ['GET']
