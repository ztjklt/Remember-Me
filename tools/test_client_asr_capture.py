import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest


def load():
    spec = importlib.util.spec_from_file_location('client_capture', Path(__file__).with_name('client_asr_capture.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_raw_asr_checkpoint_is_reused_and_changed_audio_is_refused(tmp_path):
    mod = load()
    audio = tmp_path/'clip.wav'; audio.write_bytes(b'fictional')
    out = tmp_path/'draft.json'
    class Provider:
        def transcribe(self, raw, content_type):
            return SimpleNamespace(text='我沒有去過北京。', metadata={'http_status':200})
    result = mod.transcribe_recording(audio, out, Provider(), audio_export_confirmed=True)
    assert result['client_transcript']['text'] == '我沒有去過北京。'
    assert result['client_transcript']['audio_sha256'] == hashlib.sha256(b'fictional').hexdigest()
    class BrokenProvider:
        def transcribe(self, *args):
            raise AssertionError('Completed ASR must not be called again')
    assert mod.transcribe_recording(audio, out, BrokenProvider(), audio_export_confirmed=True) == result
    audio.write_bytes(b'changed')
    with pytest.raises(ValueError):
        mod.transcribe_recording(audio, out, BrokenProvider(), audio_export_confirmed=True)


def test_unknown_asr_attempt_is_not_silently_repeated(tmp_path):
    mod = load()
    audio=tmp_path/'clip.wav';audio.write_bytes(b'fictional')
    out=tmp_path/'draft.json'
    class FailingProvider:
        def transcribe(self, *args):
            raise RuntimeError('temporary failure')
    with pytest.raises(RuntimeError):
        mod.transcribe_recording(audio,out,FailingProvider(),audio_export_confirmed=True)
    assert not out.exists()
    with pytest.raises(ValueError,match='attempt'):
        mod.transcribe_recording(audio,out,FailingProvider(),audio_export_confirmed=True)


@pytest.mark.parametrize('url',['http://remote.example','https://user:secret@host','https://host?q=secret','ftp://host'])
def test_product_credentials_cannot_be_sent_to_cleartext_remote_or_url_credentials(url):
    with pytest.raises(ValueError):
        load().server_url(url)


def test_upload_binds_raw_asr_and_audio_and_never_confirms_review(tmp_path):
    mod=load()
    audio=tmp_path/'clip.wav';audio.write_bytes(b'fictional')
    draft={'audio_path':str(audio), 'client_transcript':{'text':'实际机器稿',
        'audio_sha256':hashlib.sha256(b'fictional').hexdigest(), 'provider':'groq',
        'model':'whisper-large-v3','audio_export_confirmed':True}}
    receipt=tmp_path/'upload.json'
    def handler(request):
        assert request.url == 'https://service.example/api/v1/episodes/client-transcribed'
        assert request.method == 'POST'
        assert '实际机器稿'.encode() in request.content and b'fictional' in request.content
        assert b'IMPORT' in request.content
        return httpx.Response(201,json={'episode_id':'ep_test','upload_status':'uploaded'})
    with httpx.Client(base_url='https://service.example',transport=httpx.MockTransport(handler)) as client:
        result=mod.upload_recording(client,draft,{'actor_token':'test-only-token'},
            subject_id='subject',consent_id='consent',idempotency_key='test-key',receipt=receipt)
    assert result['episode_id']=='ep_test' and receipt.exists()
    assert 'test-only-token' not in receipt.read_text()
    assert not result.get('reviewed', False)


def test_upload_receipt_cannot_be_reused_for_another_space_before_network(tmp_path):
    mod=load()
    audio=tmp_path/'clip.wav';audio.write_bytes(b'fictional')
    draft={'audio_path':str(audio),'client_transcript':{'text':'实际机器稿',
        'audio_sha256':hashlib.sha256(b'fictional').hexdigest(), 'provider':'groq',
        'model':'whisper-large-v3','audio_export_confirmed':True}}
    receipt=tmp_path/'upload.json'
    with httpx.Client(base_url='https://service.example',transport=httpx.MockTransport(
            lambda request:httpx.Response(201,json={'episode_id':'ep_test','upload_status':'uploaded'}))) as client:
        mod.upload_recording(client,draft,{'actor_token':'test-only'},subject_id='subject',
            consent_id='consent',idempotency_key='key',receipt=receipt)
    def unexpected(request):
        pytest.fail('A mismatched checkpoint sent an unwanted upload')
    with httpx.Client(base_url='https://service.example',transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError):
            mod.upload_recording(client,draft,{'actor_token':'test-only'},subject_id='other',
                consent_id='consent',idempotency_key='key',receipt=receipt)
