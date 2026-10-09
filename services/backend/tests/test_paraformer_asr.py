"""Real adapter with a simulated remote boundary; not live-model acceptance."""
import json
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.stt import build_stt_provider
from app.errors import SttFailed, SttTimeout, SttUnavailable
from app.models import Episode, Job
from app.worker import ProcessingWorker
from test_cloud_asr_consent import setup_cloud, upload

BASE = 'https://llm-test.cn-beijing.maas.aliyuncs.com'
UPLOAD = 'https://dashscope-file-bj.oss-cn-beijing.aliyuncs.com'
RESULT = 'https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/result.json?Signature=secret'


def settings(tmp_path):
    return Settings(_env_file=None, stt_backend='paraformer',
        paraformer_api_key='unit-secret', paraformer_base_url=BASE,
        paraformer_state_dir=str(tmp_path), paraformer_poll_interval_seconds=0.001,
        paraformer_poll_timeout_seconds=0.03)


class Remote:
    def __init__(self, mode='success'):
        self.requests = []; self.mode = mode; self.file_url = None

    def __call__(self, req):
        self.requests.append(req)
        if req.url.path == '/api/v1/uploads':
            return httpx.Response(200, json={'data': {'policy':'secret-policy','signature':'secret-signature',
                'upload_dir':'uploads/test', 'upload_host':UPLOAD if self.mode != 'evil' else 'https://evil.example/upload',
                'oss_access_key_id':'temporary', 'x_oss_object_acl':'private','x_oss_forbid_overwrite':'true'}})
        if req.url.host == 'dashscope-file-bj.oss-cn-beijing.aliyuncs.com':
            assert b'ORIGINAL' in req.content and 'authorization' not in req.headers
            return httpx.Response(200)
        if req.url.path.endswith('/transcription'):
            body=json.loads(req.content); self.file_url=body['input']['file_urls'][0]
            assert body['model']=='paraformer-v2' and 'prompt' not in body
            if self.mode == 'submit_timeout': raise httpx.ReadTimeout('secret',request=req)
            return httpx.Response(200,json={'output':{'task_id':'task-1','task_status':'PENDING'}})
        if req.url.path.endswith('/tasks/task-1'):
            if self.mode == 'pending': return httpx.Response(200,json={'output':{'task_id':'task-1','task_status':'RUNNING'}})
            if self.mode == 'auth': return httpx.Response(401,text='secret response')
            resolved = UPLOAD+'/'+self.file_url[6:]+'?Signature=private' if self.mode in {'resolved','wrong_file'} else self.file_url
            if self.mode=='wrong_file': resolved=UPLOAD+'/different-recording?Signature=private'
            self.resolved_file = resolved
            return httpx.Response(200,json={'usage':{'duration':3},'output':{'task_id':'task-1','task_status':'SUCCEEDED',
                'results':[{'file_url':resolved,'subtask_status':'FAILED' if self.mode=='subtask' else 'SUCCEEDED','transcription_url':RESULT}]}})
        assert req.url.host=='dashscope-result-bj.oss-cn-beijing.aliyuncs.com'
        assert 'authorization' not in req.headers
        return httpx.Response(200,json={'file_url':self.resolved_file,'transcripts':[
            {'channel_id':0,'text':'' if self.mode=='empty' else '我沒有去過北京。'}]})


def wired(tmp_path, monkeypatch, remote):
    from app import paraformer_asr
    real_client = httpx.Client
    monkeypatch.setattr(paraformer_asr, '_client', lambda timeout: real_client(transport=httpx.MockTransport(remote), timeout=timeout))
    return build_stt_provider(settings(tmp_path))


def test_factory_requires_explicit_provider_and_credentials(tmp_path):
    cfg=settings(tmp_path); cfg.paraformer_api_key=SecretStr('')
    with pytest.raises(SttFailed): build_stt_provider(cfg).transcribe(b'ORIGINAL','audio/mp4')


def test_launcher_does_not_silently_replace_paraformer():
    from run_workbench import prepare_runtime
    env, _, commands = prepare_runtime({'REMEMBER_STT_BACKEND':'paraformer'}, {})
    assert env['REMEMBER_STT_BACKEND']=='paraformer'
    assert not any('app.local_stt:app' in str(command) for command in commands)


def test_audio_only_private_upload_and_raw_text_provenance(tmp_path,monkeypatch):
    remote=Remote(); provider=wired(tmp_path,monkeypatch,remote)
    result=provider.transcribe(b'ORIGINAL','audio/mp4')
    assert result.text=='我沒有去過北京。' and result.backend=='paraformer'
    assert result.metadata['request_model']=='paraformer-v2' and result.metadata['response_model'] is None
    audit=(tmp_path/'calls.jsonl').read_text()
    assert 'unit-secret' not in audit and 'Signature=' not in audit and result.text not in audit
    assert result.metadata['task_id']=='task-1'


def test_signed_result_url_is_not_exposed_by_http_library_logs(tmp_path,monkeypatch,caplog):
    import logging
    from app.logging_config import configure_logging
    # Production logging setup must quiet request URLs even when app logs INFO.
    configure_logging('INFO')
    captured=[]
    class Capture(logging.Handler):
        def emit(self, record): captured.append(record.getMessage())
    handler=Capture(); logging.getLogger('httpx').addHandler(handler)
    try:
        wired(tmp_path,monkeypatch,Remote()).transcribe(b'ORIGINAL','audio/mp4')
    finally: logging.getLogger('httpx').removeHandler(handler)
    assert not any('Signature=secret' in message for message in captured)


def test_poll_timeout_resumes_same_task_without_upload_or_resubmit(tmp_path,monkeypatch):
    remote=Remote('pending'); provider=wired(tmp_path,monkeypatch,remote)
    with pytest.raises(SttTimeout): provider.transcribe(b'ORIGINAL','audio/mp4')
    remote.mode='success'
    assert provider.transcribe(b'ORIGINAL','audio/mp4').text=='我沒有去過北京。'
    assert sum(r.url.path.endswith('/transcription') for r in remote.requests)==1
    assert sum(r.url.path=='/api/v1/uploads' for r in remote.requests)==1


def test_bailian_resolved_file_url_still_matches_exact_uploaded_object(tmp_path,monkeypatch):
    assert wired(tmp_path,monkeypatch,Remote('resolved')).transcribe(b'ORIGINAL','audio/mp4').text=='我沒有去過北京。'


def test_resolved_file_url_cannot_substitute_another_audio(tmp_path,monkeypatch):
    with pytest.raises(SttFailed): wired(tmp_path,monkeypatch,Remote('wrong_file')).transcribe(b'ORIGINAL','audio/mp4')


@pytest.mark.parametrize('mode',['evil','subtask','empty','auth'])
def test_remote_failures_never_become_valid_transcripts(tmp_path,monkeypatch,mode):
    remote=Remote(mode); provider=wired(tmp_path,monkeypatch,remote)
    with pytest.raises(SttFailed): provider.transcribe(b'ORIGINAL','audio/mp4')
    assert all(r.url.host!='evil.example' for r in remote.requests)


def test_ambiguous_submit_never_duplicates_billable_task(tmp_path,monkeypatch):
    remote=Remote('submit_timeout'); provider=wired(tmp_path,monkeypatch,remote)
    for _ in range(2):
        with pytest.raises(SttFailed): provider.transcribe(b'ORIGINAL','audio/mp4')
    assert sum(r.url.path.endswith('/transcription') for r in remote.requests)==1


def test_revocation_after_upload_prevents_model_submission(tmp_path,monkeypatch):
    remote=Remote(); provider=wired(tmp_path,monkeypatch,remote)
    def authorize():
        if len(remote.requests)>=2: raise SttFailed('revoked')
    with pytest.raises(SttFailed): provider.transcribe_authorized(b'ORIGINAL','audio/mp4',authorize)
    assert not any(r.url.path.endswith('/transcription') for r in remote.requests)


def test_product_upload_requires_policy_and_waits_for_review(app,client,session,monkeypatch,tmp_path):
    own,headers,_=setup_cloud(app,session,monkeypatch)
    cfg=app.state.settings
    for key,value in settings(tmp_path).model_dump().items():
        if key.startswith('paraformer_') or key=='stt_backend': setattr(cfg,key,value)
    from app.cloud_asr import cloud_policy
    assert upload(client,own,headers).status_code==422
    caps=client.get('/api/v1/workbench/capabilities',headers=headers).json()
    assert caps['stt_processing']=='cloud' and caps['stt_model']=='paraformer-v2'
    result=upload(client,own,headers,{'cloud_asr_policy':cloud_policy(cfg)})
    assert result.status_code==201
    remote=Remote()
    # The fixture original bytes are sent unchanged (not a fake transcript).
    remote_original=Remote.__call__
    def handle(req):
        if req.url.host=='dashscope-file-bj.oss-cn-beijing.aliyuncs.com':
            assert b'ACTUAL-FICTIONAL-AUDIO' in req.content
            remote.requests.append(req); return httpx.Response(200)
        return remote_original(remote,req)
    provider=wired(tmp_path,monkeypatch,handle)
    ProcessingWorker(app.state.database,app.state.object_store,provider,app.state.ai_client).run_once()
    session.expire_all(); ep=session.get(Episode,result.json()['episode_id'])
    assert ep.stt_transcript=='我沒有去過北京。' and ep.transcript=='我没有去过北京。'
    assert ep.stt_backend=='paraformer'
    assert session.scalar(select(Job).where(Job.episode_id==ep.episode_id)).state=='waiting'
