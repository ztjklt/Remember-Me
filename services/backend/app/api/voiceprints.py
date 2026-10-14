"""Private identity status, same-recording recognition, optional voice registration."""
from fastapi import APIRouter,Depends,Request,File,Form,UploadFile
from sqlalchemy import select
from ..db import get_session
from ..models import Actor,ConsentScope,Episode,utcnow
from ..access import require_owner,Hidden,publication_lock
from ..security import current_actor
from ..voiceprint_models import VoiceIdentity
from .. import voiceprints as vp
from ..repositories.consents import ConsentRepository
from ..errors import RequestInvalid
router=APIRouter(prefix='/api/v1/subjects/{subject_id}/voice-identities',tags=['speaker-verification'])

def view(row):return {'identity_id':row.identity_id,'label':row.label,'role':row.role,'model_version':row.encoder_version,'status':'revoked' if row.revoked_at else 'registered','source_count':len(row.sources)}
@router.get('')
def listing(subject_id:str,request:Request,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    return {'available':vp.available(request.app.state.settings),'items':[view(r) for r in session.scalars(select(VoiceIdentity).where(VoiceIdentity.subject_id==subject_id,VoiceIdentity.revoked_at.is_(None)))], 'enrollment_prompt':'介绍一下自己吧，例如：你好，我叫小王，这是我自己的声音。','notice':'记住声音后，正常录音和聊天会自动匹配；声音只辅助分辨说话人，不能替代密码。'}
@router.delete('/{identity_id}')
def delete(subject_id:str,identity_id:str,request:Request,actor:Actor=Depends(current_actor),session=Depends(get_session)):
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=session.get(VoiceIdentity,identity_id)
    if not row or row.subject_id!=subject_id:raise Hidden('声音记录不存在。')
    from ..voiceprints import invalidate_identity
    invalidate_identity(session,row,request.app.state.object_store)
    return {'deleted':True}

@router.post('/recording/{episode_id}')
def inspect_recording(subject_id:str,episode_id:str,request:Request,speaker_consent_id:str=Form(...),actor:Actor=Depends(current_actor),session=Depends(get_session)):
    require_owner(session,subject_id,actor.actor_id)
    ConsentRepository(session).require_active(speaker_consent_id,subject_id=subject_id,actor_id=actor.actor_id,scope=ConsentScope.SPEAKER_IDENTIFICATION)
    row=session.get(Episode,episode_id)
    if not row or row.subject_id!=subject_id or row.actor_id!=actor.actor_id or not row.audio_object_key:raise Hidden('原音不存在。')
    data=request.app.state.object_store.get(row.audio_object_key);raw=vp.pcm(data,row.audio_content_type);engine=vp.for_app(request.app)
    from ..stt import Transcript
    from ..speaker_identification import build_report
    metadata=(row.capture_metadata or {}).get('asr_call',{})
    report=build_report(Transcript(row.transcript or '',row.stt_backend or '',row.stt_model_version or '',metadata),duration_ms=row.duration_ms or len(raw)//32)
    # Existing non-diarized recordings may only safely match if all rolling
    # windows agree. A single full-clip vector can conceal a second speaker.
    if report['identification_status']=='text_only':
        chunks=[raw[i:i+96000] for i in range(0,len(raw),96000) if len(raw[i:i+96000])>=48000]
        hits=[]
        for chunk in chunks:
            try:hits.append(vp.match(session,subject_id,engine.extract(chunk),engine.version))
            except RequestInvalid:hits.append(None)
        same=bool(hits and all(h and h.identity_id==hits[0].identity_id for h in hits))
        identity=hits[0] if same else None
        report['voiceprint_status']='matched' if identity else 'unknown'
        report['is_subject']=bool(identity and identity.role=='subject')
        report['speaker_name']=identity.label if identity else None
    else:vp.annotate(session,subject_id,raw,report,engine)
    session.commit();return report
