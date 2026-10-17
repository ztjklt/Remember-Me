from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.conversation import ConversationInput,respond
from app.api import create_app
from app.config import Settings
from app.errors import AIOutputInvalid

class Chat:
    model='fixture'
    def complete(self,system,payload,**kwargs):
        assert 'recordings' not in payload and 'history' not in payload
        self.payload=payload
        return {'answer':'听到了，你说。'},self.model


def test_social_reply_is_generated_without_personal_memory():
    chat=Chat()
    result=respond(chat,ConversationInput(question='能听见我说话吗？',intent='audio_check'))
    assert result['response_type']=='CONVERSATION'
    assert result['answer']=='听到了，你说。'
    assert chat.payload['question']=='能听见我说话吗？'


def test_endpoint_is_typed_and_uses_configured_model():
    with TestClient(create_app(Settings(_env_file=None,environment='test',provider='fixture'),
            persona_provider=SimpleNamespace(chat=Chat()))) as client:
        response=client.post('/conversation',json={'question':'你好','intent':'greeting'})
        assert response.status_code==200, response.text
        assert response.json()['response_type']=='CONVERSATION'
        assert client.post('/conversation',json={'question':'你好','intent':'memory'}).status_code==422


def test_personal_fact_or_old_unknown_in_social_output_is_not_published():
    for text in ['我的名字叫王浩宇','这个我还说不准。']:
        chat=SimpleNamespace(model='fixture',complete=lambda *a,**k:({'answer':text},'fixture'))
        with pytest.raises(AIOutputInvalid):respond(chat,ConversationInput(question='你好',intent='greeting'))


def test_social_call_uses_same_bounded_transport_policy_as_voice():
    from contextlib import contextmanager
    class BoundedChat(Chat):
        scope=None
        @contextmanager
        def transport_scope(self,**policy):
            self.scope=policy
            try: yield
            finally:self.scope=None
        def complete(self,*args,**kwargs):
            assert self.scope['timeout_seconds']==8
            assert self.scope['json_hedged'] is True
            assert self.scope['json_retry_after_seconds']==2.8
            return super().complete(*args,**kwargs)
    settings=Settings(_env_file=None,environment='test',provider='fixture',
        voice_call_timeout_seconds=8,voice_json_retry_after_seconds=2.8,voice_json_hedged=True)
    with TestClient(create_app(settings,persona_provider=SimpleNamespace(chat=BoundedChat()))) as client:
        response=client.post('/conversation',json={'question':'你好','intent':'greeting'})
        assert response.status_code==200,response.text
