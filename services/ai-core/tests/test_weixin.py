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
    candidate={'domain':'PREFERENCES','statement':'喜欢散步','context':'日常','evidence_ids':['s1'],'counter_evidence_ids':[],'kind':'habit'}
    class Chat:
        def complete(self,*args):
            return {'candidates':[candidate]}, 'actual'
    provider=ProfileProposalProvider(Chat())
    payload=ProfileProposalInput(materials=[{'evidence_id':'ev1','episode_id':'ep1','excerpt':'每天散步'}])
    assert provider.propose(payload).prompt_version=='profile-proposals-evidence-v3'
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
        assert response.json()=={'candidates':[],'model_version':'DeepSeek-actual','prompt_version':'profile-proposals-evidence-v3'}
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


@pytest.mark.parametrize('change', ['extra_top','extra_candidate','bad_confidence','bad_domain','nonobject','too_many'])
def test_extraction_rejects_malformed_compact_candidates(change):
    from app.extractor import MemoryExtractor
    from app.contracts import AICoreInput
    from app.providers.weixin import WeixinProvider
    candidate={'quote':'source','statement':'statement','domain':'PREFERENCES','memory_type':'PREFERENCE','confidence':.8}
    raw={'memories':[candidate]}
    if change=='extra_top': raw['unexpected']=True
    elif change=='extra_candidate': candidate['status']='approved'
    elif change=='bad_confidence': candidate['confidence']='0.8'
    elif change=='bad_domain': candidate['domain']='invented'
    elif change=='nonobject': raw['memories']=[None]
    elif change=='too_many': raw['memories']=[candidate]*25
    def handle(req):
        return httpx.Response(200,json={'model':'DeepSeek-actual','choices':[{'finish_reason':'stop','message':{'content':json.dumps(raw)}}]})
    provider=WeixinProvider(api_key='test-only',client=httpx.Client(transport=httpx.MockTransport(handle)))
    payload=AICoreInput(episode_id='ep1',subject_id='s1',transcript='source',trace_id='t1',existing_model_version='v1')
    with pytest.raises(AIOutputInvalid):
        MemoryExtractor(provider=provider,model='Deepseek-v4-flash',model_version='requested').process(payload)

@pytest.mark.parametrize('length,valid', [(200,True),(201,False)])
def test_twin_answer_bound_counts_unicode_codepoints(length,valid):
    from app.providers.weixin import WeixinTwinProvider
    from app.twin import TwinInput
    provider=WeixinTwinProvider(api_key='test-only')
    provider.complete=lambda *args: ({'answer':'\u6211'*length,'response_type':'SIMULATION','evidence_ids':['ev1'],'confidence':.5},'actual')
    payload=TwinInput(question='question',candidates=[{'memory_item_id':'m1','statement':'statement','evidence':[{'evidence_id':'ev1','excerpt':'source','source_type':'SUBJECT'}]}])
    try:
        if valid:
            assert len(provider.answer(payload).answer)==200
        else:
            with pytest.raises(AIOutputInvalid): provider.answer(payload)
    finally:
        provider.close()


def test_original_router_copies_selected_source_instead_of_model_paraphrase():
    from app.providers.weixin import WeixinTwinProvider
    from app.twin import TwinInput
    provider = WeixinTwinProvider(api_key='test-only')
    # Real failure: the model selected the correct evidence but rewrote person
    # and punctuation while labelling the result ORIGINAL.
    provider.complete = lambda *args: ({'answer':'他常对女儿说平安回家比多跑一趟重要。',
        'response_type':'ORIGINAL','evidence_ids':['ev1'],'confidence':.95}, 'actual')
    quote = '后来我常对女儿说平安回家比多跑一趟重要'
    payload = TwinInput(question='说过什么？', candidates=[{'memory_item_id':'m1','statement':quote,
        'evidence':[{'evidence_id':'ev1','excerpt':quote,'source_type':'SUBJECT'}]}])
    try:
        output = provider.answer(payload)
        assert output.answer == quote
        assert output.response_type == 'ORIGINAL'
    finally:
        provider.close()


@pytest.mark.parametrize('ids,source,length', [(['bad'],'SUBJECT',20),(['ev1','ev2'],'SUBJECT',20),(['ev1'],'AI_INFERENCE',20),(['ev1'],'SUBJECT',201)])
def test_original_router_refuses_ambiguous_inferred_or_oversized_source(ids,source,length):
    from app.providers.weixin import WeixinTwinProvider
    from app.twin import TwinInput
    provider = WeixinTwinProvider(api_key='test-only')
    provider.complete = lambda *args: ({'answer':'','response_type':'ORIGINAL','evidence_ids':ids,'confidence':.9}, 'actual')
    payload = TwinInput(question='问题', candidates=[{'memory_item_id':'m1','statement':'材料',
        'evidence':[{'evidence_id':eid,'excerpt':'字'*length,'source_type':source} for eid in ['ev1','ev2']]}])
    try:
        with pytest.raises(AIOutputInvalid): provider.answer(payload)
    finally:
        provider.close()


def test_profile_uses_short_source_handles_and_explicit_schema():
    from app.profile_proposals import ProfileProposalProvider, ProfileProposalInput
    class Chat:
        def complete(self, system, payload):
            assert 'additionalProperties' in system and 'required' in system
            assert payload['materials'][0]['evidence_id'] == 's1'
            return {'candidates':[{'domain':'PREFERENCES','kind':'habit','statement':'喜欢散步',
                'context':'本人描述日常散步','evidence_ids':['s1'],'counter_evidence_ids':[]}]}, 'actual'
    result = ProfileProposalProvider(Chat()).propose(ProfileProposalInput(materials=[
        {'evidence_id':'src_very_long_identifier','episode_id':'ep1','excerpt':'我每天散步'}]))
    assert result.candidates[0].evidence_ids == ['src_very_long_identifier']


def test_unsupported_extraction_quote_is_failure_not_successful_empty_memory():
    from app.extractor import MemoryExtractor
    from app.contracts import AICoreInput
    from app.providers.weixin import WeixinProvider
    provider=WeixinProvider(api_key='test-only')
    provider.complete=lambda *args: ({'memories':[{'quote':'我喜欢游泳','statement':'喜欢游泳',
        'domain':'PREFERENCES','memory_type':'PREFERENCE','confidence':.9}]}, 'actual')
    try:
        with pytest.raises(AIOutputInvalid):
            MemoryExtractor(provider=provider,model='Deepseek-v4-flash',model_version='requested').process(
                AICoreInput(episode_id='ep1',subject_id='s1',transcript='我喜欢散步',existing_model_version='v1'))
    finally:provider.close()


@pytest.mark.parametrize('source_id,valid',[('s1',True),('unknown',False)])
def test_extraction_source_selection_uses_actual_text_not_model_retyping(source_id,valid):
    from app.providers.weixin import WeixinProvider
    from app.contracts import AICoreInput
    from app.extractor import MemoryExtractor
    p=WeixinProvider(api_key='test-only')
    p.complete=lambda *args:({'memories':[{'source_id':source_id,'statement':'邻居偶尔来串门',
        'domain':'RELATIONSHIPS','memory_type':'RELATIONSHIP','confidence':.8}]},'actual')
    try:
        request=AICoreInput(episode_id='ep1',subject_id='s1',transcript='邻居王老师偶尔来串门。',existing_model_version='v1')
        if not valid:
            with pytest.raises(AIOutputInvalid):MemoryExtractor(provider=p,model='model',model_version='model').process(request)
        else:
            result=MemoryExtractor(provider=p,model='model',model_version='model').process(request)
            assert result.evidence[0].excerpt=='邻居王老师偶尔来串门。'
            assert result.evidence[0].span_start==0
    finally:p.close()


def test_profile_wire_evidence_alias_is_lossless_and_still_grounded():
    candidate = {'domain':'PREFERENCES','kind':'trait','statement':'喜欢散步',
                 'context':'日常','evidence':['s1'],'counter_evidence_ids':[]}
    class Chat:
        def complete(self,*args): return {'candidates':[candidate]}, 'actual'
    payload=ProfileProposalInput(materials=[{'evidence_id':'ev1','episode_id':'ep1','excerpt':'我喜欢散步'}])
    provider=ProfileProposalProvider(Chat())
    result=provider.propose(payload)
    assert result.candidates[0].evidence_ids==['ev1']
    assert 'evidence' not in result.candidates[0].model_dump()
    # Ambiguous aliases, unknown handles, illegal domains and arbitrary extras
    # must still be rejected, not dropped or guessed.
    candidate['evidence_ids']=['s1']
    with pytest.raises(AIOutputInvalid): provider.propose(payload)
    candidate.pop('evidence_ids')
    candidate['evidence']=['unknown']
    with pytest.raises(AIOutputInvalid): provider.propose(payload)
    candidate['evidence']=['s1'];candidate['domain']='HABITS'
    with pytest.raises(AIOutputInvalid): provider.propose(payload)
    candidate['domain']='PREFERENCES';candidate['approved']=True
    with pytest.raises(AIOutputInvalid): provider.propose(payload)
