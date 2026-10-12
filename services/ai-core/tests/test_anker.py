import httpx
import pytest
from app.config import Settings
from app.errors import AIOutputInvalid, ProviderAuthenticationFailed
from app.providers.anker import AnkerChat, AnkerTwinProvider, BASE_URL
from app.twin import TwinInput

MODEL = 'hackathon/v_model/qwen-max'


def test_route_authentication_failure_is_safe_and_no_redirect():
    calls = []
    def remote(request):
        calls.append(request)
        return httpx.Response(401, text='fixture private response')
    with httpx.Client(transport=httpx.MockTransport(remote)) as client:
        chat = AnkerChat(api_key='fixture-key', model=MODEL, client=client)
        with pytest.raises(ProviderAuthenticationFailed) as error:
            chat.complete('fixture JSON', {'text': 'fixture source'})
        assert 'private response' not in str(error.value)
        assert len(calls) == 1
        assert str(calls[0].url) == BASE_URL + '/chat/completions'
    with pytest.raises(ValueError):
        AnkerChat(api_key='fixture-key', model=MODEL, base_url='https://other.invalid')


def test_router_model_identity_and_unknown_citation_validation():
    def remote(_):
        return httpx.Response(200, json={'model': 'qwen-actual-version', 'choices': [
            {'finish_reason': 'stop', 'message': {'content': '{"status":"ok"}'}}]})
    with httpx.Client(transport=httpx.MockTransport(remote)) as client:
        chat = AnkerChat(api_key='fixture-key', model=MODEL, client=client)
        assert chat.complete('fixture JSON', {}) == ({'status': 'ok'}, 'qwen-actual-version')
        twin = AnkerTwinProvider(api_key='fixture-key', model=MODEL, client=client, verify_answers=False)
        twin.complete = lambda *_: ({'answer': '', 'response_type': 'ORIGINAL',
            'evidence_ids': ['s1'], 'confidence': .9}, 'qwen-actual-version')
        payload = TwinInput(question='计划确定了吗', candidates=[{'memory_item_id': 'm1',
            'statement': '尚未决定', 'evidence': [{'evidence_id': 'actual-source',
            'source_type': 'SUBJECT', 'excerpt': '我还没有决定。'}]}])
        result = twin.answer(payload)
        assert result.answer == '我还没有决定。'
        assert result.evidence_ids == ['actual-source']
        assert result.model_version == 'qwen-actual-version'
        twin.complete = lambda *_: ({'answer': '', 'response_type': 'ORIGINAL',
            'evidence_ids': ['invented'], 'confidence': .9}, 'qwen-actual-version')
        with pytest.raises(AIOutputInvalid): twin.answer(payload)


def test_anker_settings_do_not_accept_other_destination():
    params = dict(AI_PROVIDER='anker', AI_API_KEY='fixture-key', AI_MODEL=MODEL,
        AI_MODEL_VERSION=MODEL, AI_BASE_URL=BASE_URL, REMEMBER_ENVIRONMENT='staging')
    assert Settings(**params).provider == 'anker'
    params['AI_BASE_URL'] = 'https://api.deepseek.com'
    with pytest.raises(ValueError): Settings(**params)
