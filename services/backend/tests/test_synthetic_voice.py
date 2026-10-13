"""Real API authorization and persistence; provider/network boundaries are fixtures."""
import io
import wave

import pytest
from sqlalchemy import select

from app.models import Episode, StoryGrant, VoiceAsset, VoiceProfile
from test_agent_workbench import setup_pair


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 1600)
    return out.getvalue()


class SyntheticProvider:
    model = 'mimo-v2.5-tts-voiceclone'
    calls = 0
    on_call = None

    def synthesize(self, text, sample, transcript):
        self.calls += 1
        assert text == '我喜欢散步'
        assert sample == wav_bytes()
        if self.on_call:
            self.on_call()
        return wav_bytes(), 'mimo-v2.5-tts-voiceclone-202610'


def prepare(app, client, session, tmp_path):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    root = f'/api/v1/subjects/{owner.subject_id}'
    voice = client.post('/api/v1/consents', headers=oh,
        json={'subject_id':owner.subject_id, 'scope':'VOICE'}).json()['consent_id']
    reference = tmp_path / 'a01.wav'; reference.write_bytes(wav_bytes())
    settings = app.state.settings
    settings.voice_synthetic_backend = 'xiaomi'
    settings.a01_voice_subject_id = owner.subject_id
    settings.a01_voice_reference_path = str(reference)
    app.state.synthetic_voice_client = SyntheticProvider()
    grant = client.post(f'/api/v1/workbench/subjects/{owner.subject_id}/grants', headers=oh,
        json={'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,
              'cloud_processing_allowed':True})
    assert grant.status_code == 201, grant.text
    return owner, reader, oh, rh, ep, cloud, voice, root, grant.json()['grant_id']


def enroll(client, root, oh, voice):
    result = client.post(root+'/voice/profile/synthetic', headers=oh,
        json={'preset':'a01','voice_consent_id':voice})
    assert result.status_code == 200, result.text
    return result.json()


def answer(client, root, headers, consent):
    result = client.post(root+'/twin/answers',headers=headers,
        json={'question':'喜欢什么？','cloud_consent_id':consent})
    assert result.status_code == 200, result.text
    return result.json()['answer_id']


def test_synthetic_enrollment_is_owner_only_and_server_allowlisted(app,client,session,tmp_path):
    owner,reader,oh,rh,ep,cloud,voice,root,grant=prepare(app,client,session,tmp_path)
    path=root+'/voice/profile/synthetic'
    payload={'preset':'a01','voice_consent_id':voice}
    assert client.post(path,headers=rh,json=payload).status_code == 404
    assert client.post(path,headers=oh,json=payload|{'reference_url':'https://evil.test/person.wav'}).status_code == 422
    assert client.post(path,headers=oh,json=payload|{'preset':'someone-else'}).status_code == 422
    assert client.post(path,headers=oh,json=payload|{'voice_consent_id':owner.consent_id}).status_code == 403
    app.state.settings.a01_voice_subject_id=reader.subject_id
    assert client.post(path,headers=oh,json=payload).status_code == 404
    app.state.settings.a01_voice_subject_id=owner.subject_id
    profile=enroll(client,root,oh,voice)
    assert profile['synthetic'] is True and profile['preset']=='a01'
    assert profile['model_version']=='mimo-v2.5-tts-voiceclone'
    assert app.state.synthetic_voice_client.calls == 0
    exposed=client.get(root+'/voice/profile',headers=rh)
    assert exposed.status_code==200 and exposed.json()['ready'] is False
    assert voice not in exposed.text and str(tmp_path) not in exposed.text


def test_voice_grant_is_separate_and_speech_uses_readers_own_saved_answer(app,client,session,tmp_path):
    owner,reader,oh,rh,ep,cloud,voice,root,grant=prepare(app,client,session,tmp_path)
    enroll(client,root,oh,voice)
    aid=answer(client,root,rh,grant); path=root+f'/twin/answers/{aid}/speech'
    assert client.post(path,headers=rh).status_code==404
    grant_path=root+f'/voice/recipients/{reader.actor_id}'
    assert client.put(grant_path,headers=rh,json={'enabled':True}).status_code==404
    allowed=client.put(grant_path,headers=oh,json={'enabled':True})
    assert allowed.status_code==200 and allowed.json()['enabled'] is True
    assert client.get(grant_path,headers=oh).json()['enabled'] is True
    assert client.post(path,headers=oh).status_code==404
    assert client.post(path,headers=rh,json={'text':'任意仿冒内容'}).status_code==422
    first=client.post(path,headers=rh); assert first.status_code==200, first.text
    assert first.json()['model_version']=='mimo-v2.5-tts-voiceclone-202610'
    assert client.post(path,headers=rh).json()['asset_id']==first.json()['asset_id']
    assert app.state.synthetic_voice_client.calls==1
    audio=root+'/voice/assets/'+first.json()['asset_id']+'/audio'
    assert client.get(audio,headers=oh).status_code==404
    assert client.get(audio,headers=rh).content==wav_bytes()
    assert client.get(audio,headers=rh).headers['cache-control']=='no-store'
    assert client.put(grant_path,headers=oh,json={'enabled':False}).status_code==200
    assert client.get(audio,headers=rh).status_code==404
    session.expire_all()
    assert session.scalar(select(VoiceAsset)) is None
    assert session.get(StoryGrant,grant).revoked_at is None


@pytest.mark.parametrize('change',['story','cloud','source','voice','owner_consent','profile','reference','disabled'])
def test_revocation_or_source_change_during_call_discards_generated_audio(app,client,session,tmp_path,change):
    owner,reader,oh,rh,ep,cloud,voice,root,grant=prepare(app,client,session,tmp_path)
    enroll(client,root,oh,voice)
    assert client.put(root+f'/voice/recipients/{reader.actor_id}',headers=oh,json={'enabled':True}).status_code==200
    aid=answer(client,root,rh,grant)
    def mutate():
        if change=='voice':
            assert client.put(root+f'/voice/recipients/{reader.actor_id}',headers=oh,json={'enabled':False}).status_code==200
        elif change=='profile':
            enroll(client,root,oh,voice)
        elif change=='owner_consent':
            assert client.post('/api/v1/consents/'+voice+'/revoke',headers=oh).status_code==200
        elif change=='disabled':
            app.state.settings.voice_synthetic_backend='disabled'
        elif change=='reference':
            (tmp_path/'a01.wav').write_bytes(b'changed')
        else:
            with app.state.database.session() as s:
                if change=='source': s.get(Episode,ep).transcript+='新变化'
                elif change=='cloud': s.get(StoryGrant,grant).cloud_processing_allowed=0
                else:
                    from app.models import utcnow
                    s.get(StoryGrant,grant).revoked_at=utcnow()
                s.commit()
    app.state.synthetic_voice_client.on_call=mutate
    result=client.post(root+f'/twin/answers/{aid}/speech',headers=rh)
    assert result.status_code in {403,404,409},result.text
    session.expire_all();assert session.scalar(select(VoiceAsset)) is None
    assert not any('/voice/answers/' in key for key in app.state.object_store._objects)


def test_cached_speech_revalidates_source_and_removes_stale_bytes(app,client,session,tmp_path):
    owner,reader,oh,rh,ep,cloud,voice,root,grant=prepare(app,client,session,tmp_path)
    enroll(client,root,oh,voice)
    aid=answer(client,root,oh,cloud); path=root+f'/twin/answers/{aid}/speech'
    speech=client.post(path,headers=oh); assert speech.status_code==200,speech.text
    audio=root+'/voice/assets/'+speech.json()['asset_id']+'/audio'
    session.get(Episode,ep).transcript+='新的来源';session.commit()
    assert client.get(audio,headers=oh).status_code in {404,409}
    assert client.post(path,headers=oh).status_code in {404,409}
    assert app.state.synthetic_voice_client.calls==1
    session.expire_all(); assert session.scalar(select(VoiceAsset)) is None


def test_invalid_owner_consent_does_not_leak_its_identifier_to_reader(app,client,session,tmp_path):
    from app.models import Consent
    owner,reader,oh,rh,ep,cloud,voice,root,grant=prepare(app,client,session,tmp_path)
    enroll(client,root,oh,voice)
    assert client.put(root+f'/voice/recipients/{reader.actor_id}',headers=oh,json={'enabled':True}).status_code==200
    aid=answer(client,root,rh,grant)
    session.get(Consent,voice).status='revoked';session.commit()
    response=client.post(root+f'/twin/answers/{aid}/speech',headers=rh)
    assert response.status_code==404
    assert voice not in response.text
    assert app.state.synthetic_voice_client.calls==0
