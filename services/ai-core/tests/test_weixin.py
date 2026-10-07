import json
import httpx
import pytest
from app.config import Settings
from app.errors import AIOutputInvalid
from app.providers.weixin import WeixinChat
from app.profile_proposals import ProfileProposalInput, ProfileProposalProvider


def test_weixin_settings_defaults_and_host_guard():
    s = Settings(_env_file=None, AI_PROVIDER='weixin', WEIXIN_CHAT_API_KEY='test-only')
    assert (s.base_url, s.model, s.timeout_seconds, s.max_concurrent_requests) == ('https://chatapi.weixin.qq.com/openai/v1', 'Deepseek-v4-flash', 45, 1)
    with pytest.raises(ValueError):
        Settings(_env_file=None, AI_PROVIDER='weixin', WEIXIN_CHAT_API_KEY='test-only', AI_BASE_URL='https://example.com')


def test_json_object_no_extras_and_actual_model():
    captured = []
    def handle(req):
        captured.append(json.loads(req.content))
        return httpx.Response(200, json={'model':'DeepSeek-V4-Flash-actual','choices':[{'finish_reason':'stop','message':{'content':'{"candidates":[]}'}}]})
    chat = WeixinChat(api_key='test-only', client=httpx.Client(transport=httpx.MockTransport(handle)))
    output, model = chat.complete('JSON only', {})
    assert output == {'candidates': []}
    assert model == 'DeepSeek-V4-Flash-actual'
    assert set(captured[0]) == {'model','messages','response_format'}
    assert captured[0]['response_format'] == {'type':'json_object'}


def test_proposal_unknown_evidence_fails():
    class Chat:
        def complete(self, *args):
            return {'candidates':[{'domain':'PREFERENCES','statement':'喜欢散步','context':'日常','evidence_ids':['invented'],'counter_evidence_ids':[],'kind':'habit'}]}, 'actual'
    provider = ProfileProposalProvider(Chat())
    with pytest.raises(AIOutputInvalid):
        provider.propose(ProfileProposalInput(materials=[{'evidence_id':'ev1','episode_id':'ep1','excerpt':'每天散步'}]))

@pytest.mark.parametrize('status,error', [(401,'AI_AUTH_FAILED'),(403,'AI_AUTH_FAILED'),(429,'AI_UNAVAILABLE'),(500,'AI_UNAVAILABLE'),(504,'AI_TIMEOUT'),(400,'AI_SCHEMA_INVALID')])
def test_failure_classes_one_upstream_attempt(status, error):
    calls = []
    def handle(req):
        calls.append(req)
        return httpx.Response(status, json={})
    chat = WeixinChat(api_key='test-only', client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(Exception) as caught:
        chat.complete('JSON', {})
    assert caught.value.code == error
    assert len(calls) == 1

@pytest.mark.parametrize('content,finish', [('{','stop'),('{"candidates":[]}','length'),('{"x":NaN}','stop')])
def test_malformed_truncated_nonfinite_fail_without_retry(content,finish):
    calls=[]
    def handle(req):
        calls.append(req)
        return httpx.Response(200,json={'model':'Deepseek-v4-flash','choices':[{'finish_reason':finish,'message':{'content':content}}]})
    chat=WeixinChat(api_key='test-only', client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(AIOutputInvalid):
        chat.complete('JSON',{})
    assert len(calls)==1


def test_profile_schema_rejects_status_confidence_and_unknown_counter_evidence():
    candidate={'domain':'PREFERENCES','statement':'喜欢散步','context':'日常','evidence_ids':['ev1'],'counter_evidence_ids':[],'kind':'habit'}
    class Chat:
        def complete(self,*args):
            return {'candidates':[candidate]}, 'actual'
    provider=ProfileProposalProvider(Chat())
    payload=ProfileProposalInput(materials=[{'evidence_id':'ev1','episode_id':'ep1','excerpt':'每天散步'}])
    assert provider.propose(payload).prompt_version=='profile-proposals-evidence-v1'
    candidate['confidence']=.9
    with pytest.raises(AIOutputInvalid):
        provider.propose(payload)
    candidate.pop('confidence')
    candidate['counter_evidence_ids']=['unknown']
    with pytest.raises(AIOutputInvalid):
        provider.propose(payload)


def test_proposal_http_worker_has_fixed_versions_and_bounded_input():
    from fastapi.testclient import TestClient
    from app.api import create_app
    class Chat:
        def complete(self,*args):
            return {'candidates':[]}, 'DeepSeek-actual'
    with TestClient(create_app(Settings(_env_file=None), profile_provider=ProfileProposalProvider(Chat()))) as client:
        response=client.post('/profile-proposals',json={'materials':[{'evidence_id':'ev1','episode_id':'ep1','excerpt':'原话'}]})
        assert response.status_code==200
        assert response.json()=={'candidates':[],'model_version':'DeepSeek-actual','prompt_version':'profile-proposals-evidence-v1'}
        assert client.post('/profile-proposals',json={'materials':[],'prompt_version':'invented'}).status_code==422


def test_extraction_keeps_actual_uppercase_model_and_offsets():
    from app.extractor import MemoryExtractor
    from app.contracts import AICoreInput
    from app.providers.weixin import WeixinProvider
    raw={'memories':[{'quote':'我喜欢散步','statement':'喜欢散步','domain':'PREFERENCES','memory_type':'PREFERENCE','confidence':.8}]}
    def handle(req):
        return httpx.Response(200,json={'model':'DeepSeek-Actual','choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]})
    provider=WeixinProvider(api_key='test-only',client=httpx.Client(transport=httpx.MockTransport(handle)))
    output=MemoryExtractor(provider=provider,model='Deepseek-v4-flash',model_version='requested').process(AICoreInput(episode_id='ep1',subject_id='s1',transcript='我喜欢散步',trace_id='t1',existing_model_version="v1"))
    assert output.model_version=='DeepSeek-Actual'
    assert output.memory_items[0].model_version=='DeepSeek-Actual'
    assert output.evidence[0].excerpt=='我喜欢散步'

