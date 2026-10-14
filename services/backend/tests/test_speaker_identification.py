import json
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.stt import Transcript
from app.errors import SttFailed, SttTimeout
from app.speaker_identification import build_report, run_one
from app.speaker_models import SpeakerRecording
from app.models import Episode, VoiceProfile, MemoryItem, utcnow
from app.seed import seed_development_data
from app import speaker_identification as recognition


def utterance(text, speaker=0, start=0, end=4000):
    return {'text': text, 'speaker_id': speaker, 'begin_time': start, 'end_time': end}


def transcript(rows): return Transcript('fake test transcript', 'fixture', 'fixture-diarization', {'speaker_sentences': rows})


def rows():
    return [utterance('我是小王。我同意录音、云端转写和本次声音识别。'),
            utterance('我是小李。我同意录音、云端转写和本次声音识别。',1,4500,8500),
            utterance('那天我们去种树。',0,9000,13000),utterance('我还记得那棵树。',1,14000,18000)]


def test_self_introduction_labels_later_speech_without_manual_confirmation():
    report=build_report(transcript(rows()),duration_ms=20000)
    assert [s['speaker_name'] for s in report['segments']]==['小王','小李','小王','小李']
    assert report['identification_scope']=='recording'
    assert report['speakers'][0]['consent_segment_ids']==['segment_0']


def test_same_name_does_not_merge_different_acoustic_speakers():
    report=build_report(transcript([utterance('我是小王。我同意录音、转写和声音识别。'),
        utterance('我是小王。我同意录音、转写和声音识别。',1,5000,9000)]),duration_ms=10000)
    assert len(report['speakers'])==2
    assert report['speakers'][0]['speaker_id']!=report['speakers'][1]['speaker_id']


@pytest.mark.parametrize('text',['他说我是小王。','我是你的朋友。','我是老师。','我是小王。'])
def test_mentions_roles_and_missing_individual_consent_do_not_establish_identity(text):
    report=build_report(transcript([utterance(text)]),duration_ms=5000)
    assert report['segments'][0]['speaker_name'] is None


def test_conflicting_introductions_and_overlap_remain_unknown():
    report=build_report(transcript([utterance('我是小王。我同意录音、转写和声音识别。'),
        utterance('我是小李。',0,5000,7000),utterance('我叫小张。我同意录音、转写和声音识别。',1,6000,9000)]),duration_ms=10000)
    # Conflicting label outside overlap is also rejected.
    report2=build_report(transcript([utterance('我是小王。我同意录音、转写和声音识别。'),
        utterance('我是小李。',0,5000,7000)]),duration_ms=10000)
    assert all(s['speaker_name'] is None for s in report2['segments'])
    assert report2['speakers'][0]['identity_method']=='conflicting_introduction'
    assert report['segments'][1]['attribution']=='overlap'
    assert report['segments'][2]['speaker_name'] is None


@pytest.mark.parametrize('speaker',[None,True,'0',-1])
def test_missing_or_invalid_acoustic_id_never_uses_first_person_text_as_identity(speaker):
    report=build_report(transcript([utterance('我是小王。我同意录音、转写和声音识别。',speaker)]),duration_ms=5000)
    assert report['segments'][0]['speaker_name'] is None


@pytest.mark.parametrize('raw',[None,[],[{'text':'我是小王','begin_time':True,'end_time':10}],
    [utterance('我是小王',start=10,end=8)],[utterance('我是小王',end=100000)]])
def test_invalid_or_missing_diarization_is_not_success(raw):
    with pytest.raises(SttFailed):build_report(Transcript('x','fixture','fixture',{'speaker_sentences':raw}),duration_ms=5000)


def prepare(app,client,session,monkeypatch):
    own=seed_development_data(session,subject_name='虚构多人测试',actor_name='本人')
    headers={'Authorization':'Bearer '+own.actor_token}
    monkeypatch.setattr(recognition,'available',lambda settings:True)
    monkeypatch.setattr(recognition,'policy',lambda settings:'fixture-policy')
    consent=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':'SPEAKER_IDENTIFICATION'}).json()['consent_id']
    return own,headers,consent


def upload(client,own,headers,consent,**overrides):
    data={'consent_id':consent,'policy':'fixture-policy','idempotency_key':'fixture-group','duration_ms':20000,
          'recorded_at':'2026-10-15T00:00:00Z','participant_consents_confirmed':'true',**overrides}
    return client.post(f'/api/v1/subjects/{own.subject_id}/speaker-recordings',headers=headers,data=data,
                       files={'file':('sample.wav',b'SYNTHETIC-AUDIO','audio/wav')})


class Provider:
    def __init__(self,callback=None,error=None):self.callback=callback;self.error=error;self.calls=0
    def transcribe_authorized(self,audio,kind,authorize,*,diarization=False):
        self.calls+=1;assert diarization;authorize()
        if self.callback:self.callback()
        authorize()
        if self.error:raise self.error
        return transcript(rows())


def test_private_idempotent_capture_process_and_no_person_or_voice_pollution(app,client,session,monkeypatch):
    own,h,c=prepare(app,client,session,monkeypatch)
    response=upload(client,own,h,c);assert response.status_code==201,response.text
    assert upload(client,own,h,c).json()['recording_id']==response.json()['recording_id']
    assert upload(client,own,h,c,duration_ms=22000).status_code==409
    assert upload(client,own,h,c,participant_consents_confirmed='false').status_code==422
    assert upload(client,own,h,own.consent_id,idempotency_key='wrong-scope').status_code==403
    rid=response.json()['recording_id'];provider=Provider()
    assert run_one(app.state.database,app.state.object_store,app.state.settings,rid,provider)
    result=client.get(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}',headers=h)
    assert result.status_code==200,result.text
    assert result.json()['report']['segments'][3]['speaker_name']=='小李'
    assert not run_one(app.state.database,app.state.object_store,app.state.settings,rid,provider)
    assert provider.calls==1
    session.expire_all()
    assert session.scalar(select(Episode)) is None
    assert session.scalar(select(MemoryItem)) is None
    assert session.scalar(select(VoiceProfile)) is None
    other=seed_development_data(session,subject_name='其他人物',actor_name='另一人')
    assert client.get(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}',headers={'Authorization':'Bearer '+other.actor_token}).status_code==404
    assert client.get(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}').status_code==401


def test_revoke_during_remote_wait_discards_late_result_and_audio(app,client,session,monkeypatch):
    own,h,c=prepare(app,client,session,monkeypatch);rid=upload(client,own,h,c).json()['recording_id']
    provider=Provider(callback=lambda:client.post('/api/v1/consents/'+c+'/revoke',headers=h))
    run_one(app.state.database,app.state.object_store,app.state.settings,rid,provider)
    response=client.get(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}',headers=h).json()
    assert response['status']=='revoked' and response['report'] is None
    assert client.get(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}/audio',headers=h).status_code==403
    session.expire_all();assert not session.get(SpeakerRecording,rid).audio_key


def test_timeout_resumes_same_record_and_delete_blocks_late_publish(app,client,session,monkeypatch):
    own,h,c=prepare(app,client,session,monkeypatch);rid=upload(client,own,h,c).json()['recording_id']
    run_one(app.state.database,app.state.object_store,app.state.settings,rid,Provider(error=SttTimeout('pending')))
    session.expire_all();assert session.get(SpeakerRecording,rid).status=='uploaded'
    run_one(app.state.database,app.state.object_store,app.state.settings,rid,
            Provider(callback=lambda:client.delete(f'/api/v1/subjects/{own.subject_id}/speaker-recordings/{rid}',headers=h)))
    session.expire_all();row=session.get(SpeakerRecording,rid)
    assert row.status=='deleted' and row.report is None and not row.audio_key


def test_repeated_revocation_preserves_deleted_tombstone_and_does_not_relist(app,client,session,monkeypatch):
    own,h,c=prepare(app,client,session,monkeypatch)
    rid=upload(client,own,h,c).json()['recording_id']
    prefix=f'/api/v1/subjects/{own.subject_id}/speaker-recordings'
    assert client.delete(prefix+'/'+rid,headers=h).json()['status']=='deleted'
    for _ in range(2):
        assert client.post('/api/v1/consents/'+c+'/revoke',headers=h).status_code==200
        assert client.get(prefix+'/'+rid,headers=h).json()['status']=='deleted'
        assert client.get(prefix,headers=h).json()['items']==[]
    session.expire_all();row=session.get(SpeakerRecording,rid)
    assert row.report is None and row.audio_key==''
