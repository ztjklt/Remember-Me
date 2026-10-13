"""Failed uploads must not leave private blobs; raw ASR is not the review draft."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.persona_models import CompanionAudio
from app.stt import Transcript
from test_companion import prepare, permission


@pytest.mark.parametrize('failure',['put','commit'])
def test_failed_upload_cleans_new_object_and_same_key_can_retry(app,client,session,monkeypatch,failure):
    owner,author,reader,oh,ah,rh,ep,root=prepare(app,client,session)
    permission(client,root,oh,author)
    store=app.state.object_store;before=set(store._objects)
    original_commit=Session.commit;original_put=store.put
    def fail_commit(self):
        if any(isinstance(row,CompanionAudio) for row in self.new):
            self.flush()
            raise RuntimeError('injected commit failure')
        return original_commit(self)
    def fail_put(key,data,mime):
        original_put(key,data,mime)
        raise RuntimeError('injected partial put failure')
    if failure=='commit':monkeypatch.setattr(Session,'commit',fail_commit)
    else:monkeypatch.setattr(store,'put',fail_put)
    body={'purpose':'contribution','idempotency_key':'recover-upload'}
    files={'file':('private.wav',b'PRIVATE-AUDIO','audio/wav')}
    with pytest.raises(RuntimeError,match='injected'):
        client.post(root+'/audio',headers=ah,data=body,files=files)
    monkeypatch.setattr(Session,'commit',original_commit);monkeypatch.setattr(store,'put',original_put)
    assert list(session.scalars(select(CompanionAudio)))==[]
    assert set(store._objects)==before
    retry=client.post(root+'/audio',headers=ah,data=body,files=files)
    assert retry.status_code==201,retry.text
    again=client.post(root+'/audio',headers=ah,data=body,files=files)
    assert again.status_code==201 and again.json()['audio_id']==retry.json()['audio_id']
    assert len(set(store._objects)-before)==1
    assert len(list(session.scalars(select(CompanionAudio))))==1


def test_asr_original_display_draft_and_review_remain_distinct(app,client,session):
    owner,author,reader,oh,ah,rh,ep,root=prepare(app,client,session)
    permission(client,root,oh,author)
    uploaded=client.post(root+'/audio',headers=ah,data={'purpose':'contribution','idempotency_key':'asr-original'},
        files={'file':('private.wav',b'PRIVATE-AUDIO','audio/wav')})
    assert uploaded.status_code==201,uploaded.text
    path=root+'/audio/'+uploaded.json()['audio_id']
    class Provider:
        def transcribe(self,audio,mime):
            return Transcript(text='我住在臺灣。',backend='http',model_version='fixture-asr')
    app.state.settings.stt_backend='http';app.state.stt_provider=Provider()
    result=client.post(path+'/transcribe',headers=ah,json={'cloud_asr_policy':'local-asr'})
    assert result.status_code==200,result.text
    body=result.json()
    assert body.get('raw_transcript_text')=='我住在臺灣。'
    assert body['transcript_text']=='我住在台湾。' and body['reviewed_text']==''
    reviewed=client.put(path+'/review',headers=ah,json={'revision':body['revision'],'text':'我以前住在台湾。'})
    assert reviewed.status_code==200,reviewed.text
    restored=client.get(path,headers=ah).json()
    assert restored['raw_transcript_text']=='我住在臺灣。'
    assert restored['transcript_text']=='我住在台湾。'
    assert restored['reviewed_text']=='我以前住在台湾。'
    assert client.get(path,headers=rh).status_code==404
    session.expire_all();saved=session.get(CompanionAudio,body['audio_id'])
    assert saved.raw_transcript_text=='我住在臺灣。'


def test_lost_commit_acknowledgement_keeps_saved_audio_for_idempotent_recovery(app,client,session,monkeypatch):
    owner,author,reader,oh,ah,rh,ep,root=prepare(app,client,session)
    permission(client,root,oh,author)
    store=app.state.object_store;before=set(store._objects);original=Session.commit
    def lose_acknowledgement(self):
        uploading=any(isinstance(row,CompanionAudio) for row in self.new)
        original(self)
        if uploading:raise RuntimeError('lost commit acknowledgement')
    monkeypatch.setattr(Session,'commit',lose_acknowledgement)
    body={'purpose':'contribution','idempotency_key':'recover-ack'}
    files={'file':('private.wav',b'PRIVATE-AUDIO','audio/wav')}
    with pytest.raises(RuntimeError,match='lost commit acknowledgement'):
        client.post(root+'/audio',headers=ah,data=body,files=files)
    monkeypatch.setattr(Session,'commit',original)
    saved=session.scalar(select(CompanionAudio))
    assert saved is not None and store.get(saved.object_key)==b'PRIVATE-AUDIO'
    retry=client.post(root+'/audio',headers=ah,data=body,files=files)
    assert retry.status_code==201,retry.text
    assert retry.json()['audio_id']==saved.audio_id
    assert len(set(store._objects)-before)==1
