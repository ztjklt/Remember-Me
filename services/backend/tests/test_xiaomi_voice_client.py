import base64
import json
import httpx
import pytest
from app.config import Settings
from app import voice_client
from test_synthetic_voice import wav_bytes


def test_clone_protocol_uses_server_reference_and_records_actual_response_model():
    requests=[]
    def respond(request):
        requests.append(request)
        body=json.loads(request.content)
        assert body['model']=='mimo-v2.5-tts-voiceclone'
        assert body['messages'][-1]=={'role':'assistant','content':'已保存的回答'}
        assert body['audio']['voice']=='data:audio/wav;base64,'+base64.b64encode(wav_bytes()).decode()
        return httpx.Response(200,json={'model':'mimo-v2.5-tts-voiceclone-202610',
            'choices':[{'finish_reason':'stop','message':{'audio':{'data':base64.b64encode(wav_bytes()).decode()}}}]})
    settings=Settings(_env_file=None,xiaomi_voice_api_key='never-print-this-key')
    adapter=voice_client.XiaomiSyntheticVoiceClient(settings,transport=httpx.MockTransport(respond))
    audio,model=adapter.synthesize('已保存的回答',wav_bytes(),'')
    assert audio==wav_bytes() and model=='mimo-v2.5-tts-voiceclone-202610'
    assert len(requests)==1


@pytest.mark.parametrize('kind',['timeout','http','missing-model','invalid-wave','truncated'])
def test_errors_are_bounded_without_secret_or_provider_body_leak(kind):
    requests=[]
    def respond(request):
        requests.append(request)
        if kind=='timeout':raise httpx.ReadTimeout('never-print-this-key',request=request)
        if kind=='http':return httpx.Response(429,text='never-print-this-key')
        body={'model':'mimo-v2.5-tts-voiceclone-202610','choices':[{'finish_reason':'stop',
            'message':{'audio':{'data':base64.b64encode(wav_bytes()).decode()}}}]}
        if kind=='missing-model':body.pop('model')
        if kind=='truncated':body['choices'][0]['finish_reason']='length'
        if kind=='invalid-wave':body['choices'][0]['message']['audio']['data']='UklGRg=='
        return httpx.Response(200,json=body)
    adapter=voice_client.XiaomiSyntheticVoiceClient(
        Settings(_env_file=None,xiaomi_voice_api_key='never-print-this-key'),transport=httpx.MockTransport(respond))
    with pytest.raises(voice_client.VoiceUnavailable) as error:
        adapter.synthesize('已保存回答',wav_bytes(),'')
    assert 'never-print-this-key' not in str(error.value)
    assert len(requests)==1
