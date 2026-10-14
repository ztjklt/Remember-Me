"""Natural dialogue material and background voice preparation; never block an answer."""
import asyncio, hashlib, io, subprocess, tempfile, wave
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, or_
from .models import Episode, Evidence, MemoryItem, ConsentScope, utcnow, as_utc
from .realtime_models import VoiceCall
from .dialogue_models import DialogueSample
from .repositories.consents import ConsentRepository
from .errors import AppError, SttFailed, SttTimeout, SttUnavailable
from .realtime_access import policy, profile_for

def consent(session, call):
    from .access import require_owner
    require_owner(session,call.subject_id,call.actor_id)
    repo=ConsentRepository(session)
    for scope,identifier in [(ConsentScope.RECORDING,call.recording_consent_id),(ConsentScope.SPEAKER_IDENTIFICATION,call.speaker_consent_id),(ConsentScope.VOICE,call.voice_consent_id)]:
        if not identifier:raise SttFailed('此通话没有启用对话采集。')
        repo.require_active(identifier,subject_id=call.subject_id,actor_id=call.actor_id,scope=scope)

def remember_turn(session,call,turn,text):
    consent(session,call)
    key='dialogue:'+call.call_id+':'+turn
    existing=session.scalar(select(Episode).where(Episode.subject_id==call.subject_id,Episode.actor_id==call.actor_id,Episode.idempotency_key==key))
    if existing:return
    identifier='ep_'+uuid4().hex;now=utcnow();mid='dialogue_'+uuid4().hex;eid='ev_'+uuid4().hex
    episode=Episode(episode_id=identifier,subject_id=call.subject_id,actor_id=call.actor_id,recording_consent_id=call.recording_consent_id,
        idempotency_key=key,source='IOS_TEXT',recorded_at=now,duration_ms=None,capture_metadata={'origin':'natural_dialogue','call_id':call.call_id,'turn_id':turn,'review_status':'pending','speaker_verification':'unverified'},
        audio_ref=None,audio_object_key=None,audio_size_bytes=0,audio_content_type='text/plain',audio_checksum=None,status='ready',trace_id='dialogue_'+uuid4().hex,
        transcript=text,stt_transcript=text,transcript_reviewed_at=None,transcript_reviewed_by=None,stt_backend='realtime-asr',stt_model_version='realtime-dialogue-v1',model_version='dialogue-input',created_at=now,updated_at=now)
    session.add(episode);session.flush()
    session.add(Evidence(evidence_id=eid,episode_id=identifier,source_type='THIRD_PARTY',source_ref='dialogue:'+call.call_id+':'+turn,excerpt=text,confidence=None))
    session.add(MemoryItem(memory_item_id=mid,episode_id=identifier,ordinal=0,memory_type='EVENT',content=text,source_type='THIRD_PARTY',evidence_ids=[eid],confidence=0,
        model_version='dialogue-input',prompt_version='natural-dialogue-v1',schema_version='0.11.0',item_metadata={'origin':'natural_dialogue','review_status':'pending','call_id':call.call_id,'turn_id':turn},review_state='pending'))
    session.commit()

def discard(session,store,row):
    row.status='deleted';row.lease_token=None;row.lease_expires_at=None
    if row.profile_id:
        from .realtime_models import RealtimeVoiceProfile
        profile=session.get(RealtimeVoiceProfile,row.profile_id)
        if profile and not profile.profile_id.startswith('rvp_default_'):
            profile.revoked_at=utcnow();profile.status='delete_pending';profile.fetch_digest='';profile.reference_text=''
            if profile.sample_key:
                try:store.delete(profile.sample_key);profile.sample_key=''
                except Exception:pass
    session.commit()
    if row.audio_key:
        try:store.delete(row.audio_key)
        except Exception:row.error='对话样本清理未完成，访问已关闭。';session.commit();return
        row.audio_key=''
    row.error=None;session.commit()

def discard_grant(session,store,identifier):
    from .voiceprint_models import VoiceUtterance
    from .voice_utterances import discard as discard_utterance
    for row in session.scalars(select(VoiceUtterance).join(VoiceCall).where(or_(VoiceCall.recording_consent_id==identifier,VoiceCall.speaker_consent_id==identifier,VoiceCall.voice_consent_id==identifier))):discard_utterance(session,store,row)
    for row in session.scalars(select(DialogueSample).join(VoiceCall).where(or_(VoiceCall.recording_consent_id==identifier,VoiceCall.speaker_consent_id==identifier,VoiceCall.voice_consent_id==identifier))):discard(session,store,row)

def validate_wave(data):
    with wave.open(io.BytesIO(data)) as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getframerate()!=16000:raise SttFailed('对话样本格式不正确。')
        ms=round(w.getnframes()/16000*1000)
        if not 5000<=ms<=15000:raise SttFailed('继续正常聊天即可，稍后再选清晰片段。')
        pcm=w.readframes(w.getnframes())
        if len(pcm)!=w.getnframes()*2:raise SttFailed('对话样本不完整。')
    return ms

def mp4(data):
    with tempfile.TemporaryDirectory(prefix='remember-dialogue-') as d:
        source=Path(d)/'input.wav';target=Path(d)/'sample.m4a';source.write_bytes(data)
        r=subprocess.run(['ffmpeg','-v','error','-i',str(source),'-ac','1','-ar','24000','-c:a','aac','-y',str(target)],capture_output=True,timeout=20)
        if r.returncode:raise SttFailed('本段声音暂不适合准备音色。')
        return target.read_bytes()

def run_one(app,provider=None):
    from .speaker_identification import available
    if not available(app.state.settings):return False
    db,store,s=app.state.database,app.state.object_store,app.state.settings;token=uuid4().hex;now=utcnow()
    with db.session() as session:
        eligible=or_(DialogueSample.status=='uploaded',(DialogueSample.status=='analyzing')&(DialogueSample.lease_expires_at<now))
        row=session.scalar(select(DialogueSample).where(eligible).order_by(DialogueSample.created_at).limit(1))
        if row is None:return False
        call=session.get(VoiceCall,row.call_id)
        try:
            consent(session,call)
            if call.policy!=policy(s):raise SttFailed('通话用途已变化。')
        except AppError:discard(session,store,row);return True
        if profile_for(session,call.subject_id,call.actor_id):discard(session,store,row);return True
        claimed=session.execute(update(DialogueSample).where(DialogueSample.sample_id==row.sample_id,eligible).values(status='analyzing',lease_token=token,lease_expires_at=now+timedelta(minutes=5),attempts=DialogueSample.attempts+1));session.commit()
        if not claimed.rowcount:return False
        identifier,key,checksum=row.sample_id,row.audio_key,row.checksum
    identity_id=None
    def authorize():
        with db.session() as session:
            current=session.get(DialogueSample,identifier);call=session.get(VoiceCall,current.call_id)
            if current.status!='analyzing' or current.lease_token!=token:raise SttFailed('样本已取消。')
            consent(session,call)
            if identity_id:
                from .voiceprint_models import VoiceIdentity
                reference=session.get(VoiceIdentity,identity_id)
                if not reference or reference.revoked_at or not reference.vectors:raise SttFailed('本人声音参考已撤销。')
            if call.policy!=policy(s):raise SttFailed('通话用途已变化。')
    try:
        authorize();data=store.get(key)
        if hashlib.sha256(data).hexdigest()!=checksum:raise SttFailed('样本校验失败。')
        validate_wave(data)
        if provider is None:
            from .paraformer_asr import ParaformerSttProvider
            cfg=s.model_copy(update={'paraformer_poll_timeout_seconds':min(15,s.paraformer_poll_timeout_seconds)})
            provider=ParaformerSttProvider(cfg,checkpoint_store=store if cfg.paraformer_checkpoint_backend=='object_store' else None)
        transcript=provider.transcribe_authorized(data,'audio/wav',authorize,diarization=True)
        rows=transcript.metadata.get('speaker_sentences',[])
        voices={r.get('speaker_id') for r in rows if isinstance(r,dict)}
        if not rows or len(voices)!=1 or any(type(v)is not int or v<0 for v in voices) or len(transcript.text.strip())<12:raise SttFailed('本段不是足够清晰的单人声音，继续聊天即可。')
        if any(max(a.get('begin_time',0),b.get('begin_time',0))<min(a.get('end_time',0),b.get('end_time',0)) for i,a in enumerate(rows) for b in rows[:i]):raise SttFailed('本段有声音重叠，继续聊天即可。')
        from .voiceprints import for_app, pcm, match
        engine=for_app(app)
        with db.session() as verification:
            current=verification.get(DialogueSample,identifier);call=verification.get(VoiceCall,current.call_id)
            identity=match(verification,call.subject_id,engine.extract(pcm(data)),engine.version)
            if not identity or identity.role!='subject':raise SttFailed('本段没有匹配本人声纹，聊天继续。')
            identity_id=identity.identity_id
        authorize();audio=mp4(data);authorize()
        def profile_created(profile_id):
            authorize()
            with db.session() as session:
                current=session.get(DialogueSample,identifier)
                current.profile_id=profile_id;session.commit()
        async def enroll():
            from starlette.requests import Request
            from starlette.datastructures import UploadFile
            from .api.realtime import enroll_profile
            from .models import Actor
            with db.session() as session:
                current=session.get(DialogueSample,identifier);call=session.get(VoiceCall,current.call_id);consent(session,call)
                request=Request({'type':'http','app':app,'headers':[], 'source_authorization':authorize,'on_profile_created':profile_created})
                return await enroll_profile(call.subject_id,request,call.voice_consent_id,transcript.text.strip()[:1000],True,call.policy,UploadFile(io.BytesIO(audio),filename='dialogue.m4a'),session.get(Actor,call.actor_id),session)
        result=asyncio.run(enroll())
        with db.session() as session:
            row=session.get(DialogueSample,identifier)
            if row.status=='analyzing' and row.lease_token==token:
                row.profile_id=result['profile_id'];row.status='prepared';row.lease_token=None;row.lease_expires_at=None;session.commit()
                store.delete(row.audio_key);row.audio_key='';session.commit()
    except Exception as exc:
        with db.session() as session:
            row=session.get(DialogueSample,identifier)
            if row.status=='analyzing' and row.lease_token==token:
                row.status='uploaded' if isinstance(exc,(SttTimeout,SttUnavailable)) and row.attempts<5 else 'skipped';row.error='本段暂未用作音色样本，正常聊天不受影响。';row.lease_token=None;row.lease_expires_at=None;session.commit()
                if row.status=='skipped':
                    try:store.delete(row.audio_key);row.audio_key='';session.commit()
                    except Exception:pass
    return True
