"""Real speaker embeddings behind an optional CPU adapter; fail closed for learning."""
import hashlib, io, math, subprocess, threading, wave
from pathlib import Path
from functools import lru_cache
from uuid import uuid4
from sqlalchemy import select
from .models import Consent, ConsentScope, utcnow
from .voiceprint_models import VoiceIdentity
from .errors import AppError, RequestInvalid
from .repositories.consents import ConsentRepository

class VoiceprintUnavailable(AppError):
    code='VOICEPRINT_UNAVAILABLE';http_status=503

class SherpaEncoder:
    def __init__(self,path):
        import sherpa_onnx
        model=Path(path)
        if not model.is_file():raise VoiceprintUnavailable('声音识别尚未准备好，录音和聊天仍可继续。')
        self.version='wespeaker-cnceleb-resnet34:'+hashlib.sha256(model.read_bytes()).hexdigest()
        config=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(model),num_threads=1,provider='cpu',debug=False)
        if not config.validate():raise VoiceprintUnavailable('声音识别暂不可用。')
        self.extractor=sherpa_onnx.SpeakerEmbeddingExtractor(config);self.lock=threading.Lock()
    def extract(self,pcm):
        import numpy as np
        a=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
        if len(a)<24000 or float(np.sqrt(np.mean(a*a)))<.003:raise RequestInvalid('声音太短或太轻，继续聊几句即可。')
        with self.lock:
            stream=self.extractor.create_stream();stream.accept_waveform(sample_rate=16000,waveform=a);stream.input_finished()
            if not self.extractor.is_ready(stream):raise RequestInvalid('本段声音不足。')
            vector=self.extractor.compute(stream)
        return unit(vector)

@lru_cache(maxsize=1)
def encoder(path):return SherpaEncoder(path)
def for_app(app):
    override=getattr(app.state,'speaker_encoder',None)
    return override if override is not None else encoder(app.state.settings.voiceprint_model_path)
def available(settings):return bool(settings.voiceprint_model_path and Path(settings.voiceprint_model_path).is_file())
def unit(vector):
    v=[float(x) for x in vector]
    norm=math.sqrt(sum(x*x for x in v))
    if not v or len(v)>4096 or not all(math.isfinite(x) for x in v) or norm<1e-8:raise RequestInvalid('声纹数据无效。')
    return [x/norm for x in v]
def similarity(a,b):return sum(x*y for x,y in zip(a,b)) if len(a)==len(b) else -1

def pcm(data,kind='audio/wav'):
    if kind in ('audio/wav','audio/x-wav'):
        try:
            with wave.open(io.BytesIO(data),'rb') as f:
                if f.getnchannels()==1 and f.getsampwidth()==2 and f.getframerate()==16000:
                    result=f.readframes(f.getnframes())
                    if len(result)!=f.getnframes()*2:raise RequestInvalid('录音不完整。')
                    return result
        except (wave.Error,EOFError):pass
    # Fixed executable/format, bounded output; no caller-controlled command args.
    try:
        r=subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-t','7200','-ac','1','-ar','16000','-f','s16le','pipe:1'],input=data,capture_output=True,timeout=45)
    except Exception as e:raise RequestInvalid('声音格式暂无法识别。') from e
    if r.returncode or not r.stdout:raise RequestInvalid('声音格式暂无法识别。')
    return r.stdout

def active(session,subject,version):
    return list(session.scalars(select(VoiceIdentity).join(Consent,VoiceIdentity.consent_id==Consent.consent_id).where(
        VoiceIdentity.subject_id==subject,VoiceIdentity.revoked_at.is_(None),VoiceIdentity.encoder_version==version,Consent.status=='granted',Consent.scope=='SPEAKER_IDENTIFICATION')))

def match(session,subject,vector,version,threshold=.70):
    scores=[]
    for row in active(session,subject,version):
        if row.vectors:
            scores.append((max(similarity(vector,unit(v)) for v in row.vectors),row))
    scores.sort(key=lambda item:item[0],reverse=True)
    if not scores or scores[0][0]<threshold or (len(scores)>1 and scores[0][0]-scores[1][0]<.08):return None
    return scores[0][1]

def enroll(session,subject,actor,consent_id,vector,version,source,*,role,label,person_key):
    from .access import require_owner
    require_owner(session,subject,actor)
    ConsentRepository(session).require_active(consent_id,subject_id=subject,actor_id=actor,scope=ConsentScope.SPEAKER_IDENTIFICATION)
    old=session.scalar(select(VoiceIdentity).where(VoiceIdentity.subject_id==subject,VoiceIdentity.person_key==person_key))
    if old and not old.revoked_at:return old # Never silently replace an existing person's acoustic reference.
    if old:session.delete(old);session.flush()
    row=VoiceIdentity(identity_id='vi_'+uuid4().hex,subject_id=subject,actor_id=actor,person_key=person_key,label=label[:80],role=role,
        consent_id=consent_id,encoder_version=version,vectors=[unit(vector)],sources=[source])
    session.add(row);session.flush();return row

def annotate(session,subject,raw,report,engine,*,consent_id=None,actor=None,source=None,learn_names=False):
    # Each candidate is extracted from non-overlapping, non-estimated ASR spans.
    groups={}
    for segment in report['segments']:
        if segment.get('overlap') or segment.get('timing_estimated') or not segment.get('speaker_id'):continue
        begin=max(0,int(segment['start_ms'])*32);end=min(len(raw),int(segment['end_ms'])*32)
        if end>begin:groups.setdefault(segment['speaker_id'],bytearray()).extend(raw[begin:end])
    for speaker in report['speakers']:
        speaker['voiceprint_status']='unknown';speaker['is_subject']=False
        try:
            data=bytes(groups.get(speaker['speaker_id'],b''))[:480000]
            vector=engine.extract(data);identity=match(session,subject,vector,engine.version)
            if identity is None and learn_names and speaker.get('name') and consent_id and actor:
                identity=enroll(session,subject,actor,consent_id,vector,engine.version,source,role='contact',label=speaker['name'],person_key='contact:'+speaker['name'])
                # A self-introduction is a label; not proof of a linked account.
                speaker['voiceprint_status']='registered_label'
            elif identity:
                speaker['voiceprint_status']='matched'
                spoken=speaker.get('name')
                if spoken and speaker.get('identity_method')=='spoken_introduction' and spoken!=identity.label:
                    identity.label=spoken # Correct a heard name using the same matched voice; never change Actor or role.
            if identity:
                speaker['voice_identity_id']=identity.identity_id;speaker['name']=identity.label
                speaker['is_subject']=identity.role=='subject' and speaker['voiceprint_status']=='matched'
        except (RequestInvalid,VoiceprintUnavailable):pass
        for segment in report['segments']:
            if segment.get('speaker_id')==speaker['speaker_id']:
                segment['voiceprint_status']=speaker['voiceprint_status'] if not segment.get('overlap') else 'unknown'
                segment['is_subject']=bool(speaker['is_subject'] and not segment.get('overlap'))
                segment['speaker_name']=speaker.get('name') if not segment.get('overlap') else None
    report['voiceprint_model_version']=engine.version
    return report

def revoke(session,identifier,store=None):
    from .models import Episode,MemoryItem
    from .repositories.person_model import PersonModelRepository
    from .retrieval import invalidate_answers
    rows=list(session.scalars(select(VoiceIdentity).where(VoiceIdentity.consent_id==identifier)))
    subjects=set()
    for row in rows:row.revoked_at=utcnow();row.vectors=[];row.sources=[];subjects.add(row.subject_id)
    for subject in subjects:
        ids={r.identity_id for r in rows if r.subject_id==subject}
        for ep in session.scalars(select(Episode).where(Episode.subject_id==subject)):
            if (ep.capture_metadata or {}).get('voice_identity_id') in ids:
                for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==ep.episode_id)):m.review_state='pending'
                ep.capture_metadata={**ep.capture_metadata,'speaker_verification':'revoked'}
        PersonModelRepository(session).rebuild(subject)
        if store:invalidate_answers(session,store,subject)
    session.commit()

def owner_registered(session,subject,settings):
    if not available(settings):return False
    try:return any(r.role=='subject' for r in active(session,subject,encoder(settings.voiceprint_model_path).version))
    except Exception:return False

def require_verified_episode(session,episode):
    identifier=(episode.capture_metadata or {}).get('voice_identity_id')
    row=session.get(VoiceIdentity,identifier) if identifier else None
    if not row or row.role!='subject' or row.subject_id!=episode.subject_id or row.revoked_at or not row.vectors:raise RequestInvalid('这条对话尚未匹配本人声音；可以继续聊，不能作为本人资料保存。')
    ConsentRepository(session).require_active(row.consent_id,subject_id=row.subject_id,actor_id=row.actor_id,scope=ConsentScope.SPEAKER_IDENTIFICATION)
    from .realtime_models import VoiceCall
    from .voiceprint_models import VoiceUtterance
    identifier=(episode.capture_metadata or {}).get('voice_utterance_id')
    utterance=session.get(VoiceUtterance,identifier) if identifier else None
    call=session.get(VoiceCall,utterance.call_id) if utterance else None
    report=(utterance.report or {}) if utterance else {}
    if not utterance or utterance.status!='ready' or not call or call.subject_id!=episode.subject_id or call.actor_id!=episode.actor_id or report.get('voiceprint_model_version')!=row.encoder_version or not any(s.get('voice_identity_id')==row.identity_id and s.get('is_subject') and s.get('voiceprint_status')=='matched' for s in report.get('speakers',[])):
        raise RequestInvalid('这条资料还没有有效的本人声纹依据。')

def invalidate_source(session,kind,identifier,store):
    rows=list(session.scalars(select(VoiceIdentity).where(VoiceIdentity.revoked_at.is_(None))))
    for row in rows:
        if any(s.get('kind')==kind and s.get('id')==identifier for s in row.sources):invalidate_identity(session,row,store)

def invalidate_identity(session,row,store):
    from .models import Episode,MemoryItem
    from .repositories.person_model import PersonModelRepository
    from .retrieval import invalidate_answers
    row.revoked_at=utcnow();row.vectors=[];row.sources=[]
    for ep in session.scalars(select(Episode).where(Episode.subject_id==row.subject_id)):
        if (ep.capture_metadata or {}).get('voice_identity_id')==row.identity_id:
            ep.capture_metadata={**ep.capture_metadata,'speaker_verification':'revoked'}
            for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id==ep.episode_id)):m.review_state='pending'
    if row.role=='subject':
        from .dialogue_models import DialogueSample
        from .realtime_models import VoiceCall
        from .dialogue_capture import discard
        for sample in session.scalars(select(DialogueSample).join(VoiceCall).where(VoiceCall.subject_id==row.subject_id)):
            discard(session,store,sample)
    PersonModelRepository(session).rebuild(row.subject_id);invalidate_answers(session,store,row.subject_id);session.commit()

def classify_recorded_evidence(episode,output):
    """Keep known other speakers out of the ordinary recording Person pipeline.

    This does not manufacture identity when an old, manually reviewed recording
    has no acoustic report. Multi-speaker reports need matched owner spans.
    """
    report=(episode.capture_metadata or {}).get('speaker_report') or {}
    speakers=report.get('speakers',[])
    if not speakers or not (len(speakers)>1 or any(s.get('voiceprint_status')=='matched' for s in speakers)):return set()
    text=episode.transcript or '';cursor=0;owner=[]
    for segment in report.get('segments',[]):
        phrase=segment.get('text','');start=text.find(phrase,cursor)
        if start<0:continue
        end=start+len(phrase);cursor=end
        if segment.get('is_subject') and not segment.get('overlap'):owner.append((start,end))
    from .contracts import SourceType
    excluded=set()
    for evidence in output.evidence:
        a,b=evidence.span_start,evidence.span_end
        if a is None or b is None or not any(a>=left and b<=right for left,right in owner):
            evidence.source_type=SourceType.THIRD_PARTY;excluded.add(evidence.evidence_id)
    for memory in output.memory_items:
        if excluded.intersection(memory.evidence_ids):memory.source_type=SourceType.THIRD_PARTY
    return excluded
