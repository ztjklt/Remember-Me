"""Background per-turn diarization. Only matched subject spans enter modeling."""
import hashlib
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select,update,or_
from .voiceprint_models import VoiceUtterance,VoiceIdentity
from .realtime_models import VoiceCall
from .models import Episode,JobStage,utcnow
from .errors import AppError
from .dialogue_capture import consent
from . import voiceprints as vp

def discard(session,store,row):
    row.status='deleted';row.report=None;row.lease_token=None;row.lease_expires_at=None;session.commit()
    vp.invalidate_source(session,'voice_utterance',row.utterance_id,store)
    if row.audio_key:
        try:store.delete(row.audio_key);row.audio_key='';session.commit()
        except Exception:pass

def run_one(app,provider=None):
    settings=app.state.settings
    if not vp.available(settings) and getattr(app.state,'speaker_encoder',None) is None:return False
    db,store=app.state.database,app.state.object_store;now=utcnow();lease=uuid4().hex
    with db.session() as session:
        eligible=or_(VoiceUtterance.status=='uploaded',(VoiceUtterance.status=='analyzing')&(VoiceUtterance.lease_expires_at<now))
        row=session.scalar(select(VoiceUtterance).where(eligible).order_by(VoiceUtterance.created_at).limit(1))
        if not row:return False
        call=session.get(VoiceCall,row.call_id)
        try:consent(session,call)
        except AppError:discard(session,store,row);return True
        hit=session.execute(update(VoiceUtterance).where(VoiceUtterance.utterance_id==row.utterance_id,eligible).values(status='analyzing',lease_token=lease,lease_expires_at=now+timedelta(minutes=5)));session.commit()
        if not hit.rowcount:return False
        identifier,key,checksum=row.utterance_id,row.audio_key,row.checksum
    def guard():
        with db.session() as session:
            row=session.get(VoiceUtterance,identifier)
            if not row or row.status!='analyzing' or row.lease_token!=lease:raise AppError('采集已停止。')
            consent(session,session.get(VoiceCall,row.call_id))
    try:
        guard();data=store.get(key)
        if hashlib.sha256(data).hexdigest()!=checksum:raise AppError('校验失败。')
        raw=vp.pcm(data);engine=vp.for_app(app)
        if provider is None:
            from .paraformer_asr import ParaformerSttProvider
            cfg=settings.model_copy(update={'paraformer_poll_timeout_seconds':min(60,settings.paraformer_poll_timeout_seconds)})
            provider=ParaformerSttProvider(cfg,checkpoint_store=store if cfg.paraformer_checkpoint_backend=='object_store' else None)
        transcript=provider.transcribe_authorized(data,'audio/wav',guard,diarization=True)
        from .speaker_identification import build_report
        report=build_report(transcript,duration_ms=len(raw)//32);guard()
        with db.session() as session:
            from .access import publication_lock
            publication_lock(session,'')
            row=session.get(VoiceUtterance,identifier);call=session.get(VoiceCall,row.call_id)
            if row.status!='analyzing' or row.lease_token!=lease:return True
            consent(session,call)
            vp.annotate(session,call.subject_id,raw,report,engine)
            # Enrollment is only an explicit initial owner operation; never
            # inferred from an arbitrary visitor saying the owner's name.
            owners=[r for r in vp.active(session,call.subject_id,engine.version) if r.role=='subject']
            clear=[s for s in report['segments'] if not s.get('overlap') and not s.get('timing_estimated')]
            if call.enroll_owner_voice and not owners and len(report['speakers'])==1 and clear:
                from .speaker_identification import _spoken_name
                label=_spoken_name(transcript.text)
                if label:
                    vp.enroll(session,call.subject_id,call.actor_id,call.speaker_consent_id,engine.extract(raw[:480000]),engine.version,{'kind':'voice_utterance','id':identifier},role='subject',label=label,person_key='subject')
                    report['owner_enrollment']='registered';call.enroll_owner_voice=False
            if report.get('owner_enrollment')!='registered' and any(s.get('name') and s.get('voiceprint_status')=='unknown' for s in report['speakers']):
                vp.annotate(session,call.subject_id,raw,report,engine,consent_id=call.speaker_consent_id,actor=call.actor_id,source={'kind':'voice_utterance','id':identifier},learn_names=True)
            for speaker in report['speakers']:
                if speaker.get('voiceprint_status')!='matched' or not speaker.get('is_subject'):continue
                spans=[s for s in clear if s.get('speaker_id')==speaker['speaker_id'] and s.get('is_subject')]
                text=''.join(s['text'] for s in spans).strip()
                if text:_remember(session,call,row.turn_id,text,speaker['voice_identity_id'],engine.version,identifier,spans,store,raw,transcript.model_version)
            row.report=report;row.status='ready';row.lease_token=None;row.lease_expires_at=None;session.commit()
            store.delete(key);row.audio_key='';session.commit()
    except Exception as exc:
        with db.session() as session:
            row=session.get(VoiceUtterance,identifier)
            if row and row.status=='analyzing' and row.lease_token==lease:
                row.report={'failure_code':getattr(exc,'code',type(exc).__name__)}
                row.status='skipped';row.lease_token=None;row.lease_expires_at=None;session.commit()
                try:store.delete(key);row.audio_key='';session.commit()
                except Exception:pass
    return True

def _remember(session,call,turn,text,identity,version,utterance,spans,store,raw,stt_version):
    from .repositories.jobs import JobRepository
    from .models import Subject
    # Legacy freezes the historical person, including the owner's voice path.
    from .entrust_models import LegacyState
    legacy=session.get(LegacyState,call.subject_id)
    if legacy and legacy.baseline and legacy.status in ('active','suspended'):return
    key='verified-dialogue:'+call.call_id+':'+turn
    if session.scalar(select(Episode).where(Episode.subject_id==call.subject_id,Episode.actor_id==call.actor_id,Episode.idempotency_key==key)):return
    now=utcnow();identifier='ep_'+uuid4().hex
    ep=Episode(episode_id=identifier,subject_id=call.subject_id,actor_id=call.actor_id,recording_consent_id=call.recording_consent_id,idempotency_key=key,
        source='IOS_TEXT',recorded_at=now,duration_ms=None,capture_metadata={'origin':'natural_dialogue','call_id':call.call_id,'turn_id':turn,'review_status':'verified','speaker_verification':'matched','voice_identity_id':identity,'speaker_model_version':version,'voice_utterance_id':utterance,'spans':spans},
        audio_size_bytes=0,audio_content_type='text/plain',status='extracting',trace_id='vp_'+uuid4().hex,transcript=text,stt_transcript=text,stt_backend='paraformer-speaker-verified',stt_model_version=stt_version,created_at=now,updated_at=now)
    pending=session.scalar(select(Episode).where(Episode.subject_id==call.subject_id,Episode.actor_id==call.actor_id,Episode.idempotency_key=='dialogue:'+call.call_id+':'+turn))
    if pending:
        ep=pending;identifier=ep.episode_id
        ep.idempotency_key=key;ep.capture_metadata={**ep.capture_metadata,'realtime_text':ep.stt_transcript,'origin':'natural_dialogue','review_status':'verified','speaker_verification':'matched','voice_identity_id':identity,'speaker_model_version':version,'voice_utterance_id':utterance,'spans':spans}
        ep.transcript=text;ep.stt_transcript=text;ep.stt_backend='paraformer-speaker-verified';ep.stt_model_version=stt_version;ep.status='extracting'
    else:session.add(ep)
    import io,wave
    original=b''.join(raw[max(0,s['start_ms']*32):min(len(raw),s['end_ms']*32)] for s in spans)
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(original)
    data=buffer.getvalue();audio_key='dialogue-originals/'+identifier+'/subject.wav'
    store.put(audio_key,data,'audio/wav')
    ep.source='IOS_MIC';ep.audio_ref='subject-dialogue.wav';ep.audio_object_key=audio_key;ep.audio_checksum=hashlib.sha256(data).hexdigest();ep.audio_size_bytes=len(data);ep.audio_content_type='audio/wav';ep.duration_ms=len(original)//32
    session.flush();job=JobRepository(session).enqueue(identifier);job.stage=str(JobStage.EXTRACT)
