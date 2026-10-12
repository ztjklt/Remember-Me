"""CloudBase lifecycle/auth checks with synthetic data; no cloud credentials."""
import importlib.util
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
import tarfile
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit
from fastapi.testclient import TestClient
from app.paraformer_asr import ParaformerSttProvider
from app.storage.memory import InMemoryObjectStore
from app.errors import SttTimeout, SttUnavailable, SttFailed
from test_paraformer_asr import Remote, settings as asr_settings

ROOT = Path(__file__).resolve().parents[3]
TOKEN = 'fixture-worker-token-' + 'a' * 32


def load_file(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env():
    return {'REMEMBER_DEPLOYMENT_SCOPE':'ios-cloudbase', 'CLOUDBASE_ENV_ID':'fixture-ios',
        'REMEMBER_DATABASE_URL':'postgresql+psycopg://fixture:fixture@db.invalid/remember_ios',
        'REMEMBER_OBJECT_STORE_BACKEND':'s3', 'REMEMBER_OBJECT_STORE_BUCKET':'remember-me-ios-fixture',
        'REMEMBER_OBJECT_STORE_ENDPOINT_URL':'https://cos.ap-shanghai.myqcloud.com',
        'CLOUDBASE_WORKER_TOKEN':TOKEN, 'REMEMBER_STT_BACKEND':'paraformer',
        'REMEMBER_PARAFORMER_BASE_URL':'https://llm-fixture.cn-beijing.maas.aliyuncs.com',
        'REMEMBER_PARAFORMER_API_KEY':'fixture-asr', 'AI_PROVIDER':'deepseek', 'AI_API_KEY':'fixture-llm'}


@pytest.mark.parametrize('key,value', [('REMEMBER_DEPLOYMENT_SCOPE','android'),
    ('REMEMBER_DATABASE_URL','sqlite:///ephemeral.db'), ('REMEMBER_OBJECT_STORE_BACKEND','local'),
    ('REMEMBER_OBJECT_STORE_BUCKET','android-originals'), ('CLOUDBASE_WORKER_TOKEN','short'),
    ('REMEMBER_OBJECT_STORE_ENDPOINT_URL','http://cos.ap-shanghai.myqcloud.com'),
    ('AI_PROVIDER','fixture')])
def test_cloudbase_rejects_shared_or_ephemeral_configuration(key, value):
    launch=load_file('cloudbase_launch', ROOT/'infra/cloudbase/runtime/launch.py')
    source=env();source[key]=value
    with pytest.raises(ValueError): launch.prepare_environment(source)


def test_cloudbase_uses_durable_checkpoints_and_keeps_registration_closed():
    launch=load_file('cloudbase_launch',ROOT/'infra/cloudbase/runtime/launch.py')
    source=env();source['REMEMBER_ALLOW_ACCOUNT_REGISTRATION']='true'
    prepared=launch.prepare_environment(source)
    assert prepared['REMEMBER_ALLOW_ACCOUNT_REGISTRATION']=='false'
    assert prepared['REMEMBER_PARAFORMER_CHECKPOINT_BACKEND']=='object_store'
    assert prepared['REMEMBER_AI_CORE_URL']=='http://127.0.0.1:8100'
    assert int(prepared['REMEMBER_MAX_UPLOAD_BYTES']) < 20*1024*1024
    assert 'REMEMBER_ENVIRONMENT' not in source
    query=parse_qs(urlsplit(prepared['REMEMBER_DATABASE_URL']).query)
    assert query['options']==['-csearch_path=remember_ios']
    assert query['sslmode']==['verify-full']


def test_database_tls_and_schema_cannot_be_disabled_by_input():
    launch=load_file('cloudbase_launch',ROOT/'infra/cloudbase/runtime/launch.py')
    source=env();source['REMEMBER_DATABASE_URL']+='?sslmode=disable&options=-csearch_path%3Dpublic'
    source['REMEMBER_POSTGRES_CA_PEM']='fixture public certificate'
    prepared=launch.prepare_environment(source)
    query=parse_qs(urlsplit(prepared['REMEMBER_DATABASE_URL']).query)
    assert query['sslmode']==['verify-full']
    assert query['options']==['-csearch_path=remember_ios']
    assert query['sslrootcert']==['/tmp/remember-postgres-ca.pem']


def test_ticks_require_separate_worker_credential_and_reject_overlap(app, monkeypatch):
    monkeypatch.setenv('CLOUDBASE_WORKER_TOKEN',TOKEN)
    runtime=load_file('cloudbase_api',ROOT/'infra/cloudbase/runtime/api.py')
    entered=threading.Event();release=threading.Event()
    class Worker:
        def run_once(self):
            entered.set()
            assert release.wait(5)
    monkeypatch.setattr(runtime,'build_worker',lambda *_:Worker())
    app.include_router(runtime.create_tick_router(app.state.database, app.state.settings, None, TOKEN))
    with TestClient(app) as client:
        for headers in ({}, {'Authorization':'Bearer fixture-actor-token'}):
            assert client.post('/internal/jobs/processing-tick',headers=headers).status_code==401
        assert not entered.is_set()
        headers={'Authorization':'Bearer '+TOKEN}
        with ThreadPoolExecutor() as executor:
            first=executor.submit(client.post,'/internal/jobs/processing-tick',headers=headers)
            try:
                assert entered.wait(5)
                assert client.post('/internal/jobs/profile-tick',headers=headers).status_code==409
            finally: release.set()
            assert first.result().json()=={'tick_completed':True}
        assert '/internal/jobs/processing-tick' not in client.get('/openapi.json').json()['paths']


def remote_provider(tmp_path, monkeypatch, remote, store):
    from app import paraformer_asr
    real_client=httpx.Client
    monkeypatch.setattr(paraformer_asr,'_client',lambda timeout:real_client(
        transport=httpx.MockTransport(remote),timeout=timeout))
    return ParaformerSttProvider(asr_settings(tmp_path),checkpoint_store=store)


def test_asr_cold_restart_resumes_existing_remote_task(tmp_path, monkeypatch):
    remote=Remote('pending');store=InMemoryObjectStore()
    with pytest.raises(SttTimeout):
        remote_provider(tmp_path/'first-instance',monkeypatch,remote,store).transcribe(b'ORIGINAL','audio/mp4')
    remote.mode='success'
    result=remote_provider(tmp_path/'replacement-instance',monkeypatch,remote,store).transcribe(b'ORIGINAL','audio/mp4')
    assert result.text=='我沒有去過北京。'
    assert sum(r.url.path.endswith('/transcription') for r in remote.requests)==1
    assert sum(r.url.path=='/api/v1/uploads' for r in remote.requests)==1


def test_uncertain_asr_submission_survives_cold_restart_without_resubmit(tmp_path, monkeypatch):
    remote=Remote('submit_timeout');store=InMemoryObjectStore()
    with pytest.raises(SttFailed):
        remote_provider(tmp_path/'first',monkeypatch,remote,store).transcribe(b'ORIGINAL','audio/mp4')
    with pytest.raises(SttFailed):
        remote_provider(tmp_path/'second',monkeypatch,remote,store).transcribe(b'ORIGINAL','audio/mp4')
    assert sum(r.url.path.endswith('/transcription') for r in remote.requests)==1


def test_unreadable_checkpoint_does_not_trigger_audio_export(tmp_path, monkeypatch):
    class UnavailableStore(InMemoryObjectStore):
        def get(self, key): raise RuntimeError('fixture storage outage')
    remote=Remote()
    with pytest.raises(SttUnavailable):
        remote_provider(tmp_path,monkeypatch,remote,UnavailableStore()).transcribe(b'ORIGINAL','audio/mp4')
    assert remote.requests==[]


def test_deploy_package_excludes_secrets_symlinks_and_local_state(tmp_path, monkeypatch):
    packaging=load_file('cloudbase_packaging',ROOT/'infra/cloudbase/package.py')
    root=tmp_path/'checkout';source=root/'services/backend/app';source.mkdir(parents=True)
    (source/'main.py').write_text('fixture source')
    (source/'.env').write_text('FIXTURE_SECRET=do-not-package')
    (source/'private.pem').write_text('fixture key')
    (source/'var').mkdir();(source/'var'/'original.m4a').write_bytes(b'fixture original')
    (source/'alias.py').symlink_to(source/'.env')
    infra=root/'infra/cloudbase';infra.mkdir(parents=True)
    (infra/'Dockerfile').write_text('FROM fixture')
    (infra/'Dockerfile.dockerignore').write_text('fixture')
    monkeypatch.setattr(packaging,'ROOT',root)
    monkeypatch.setattr(packaging,'FILES',[])
    monkeypatch.setattr(packaging,'DIRECTORIES',['services/backend/app'])
    monkeypatch.setattr(packaging.subprocess,'check_output',lambda *_args,**_kwargs:'fixture-revision\n')
    destination=root/'build'/'context'
    packaging.package(destination)
    with tarfile.open(destination.with_suffix('.tar.gz')) as archive:
        names=archive.getnames()
        assert 'services/backend/app/main.py' in names
        assert not any(name.endswith(('.env','.pem','.m4a','alias.py')) for name in names)
    with pytest.raises(ValueError): packaging.package(root/'services')


def test_timer_refuses_redirect_before_forwarding_worker_secret():
    timer=load_file('cloudbase_timer',ROOT/'infra/cloudbase/timer/index.py')
    request=urllib.request.Request('https://fixture.invalid/internal/jobs/processing-tick',
        headers={'Authorization':'Bearer '+TOKEN})
    with pytest.raises(urllib.error.HTTPError):
        timer.NoRedirect().redirect_request(request,None,302,'Found',{},'https://other.invalid')
