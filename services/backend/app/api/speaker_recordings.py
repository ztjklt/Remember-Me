"""Independent group recording capture and automatic spoken introductions."""
from datetime import datetime
from uuid import uuid4
from fastapi import APIRouter, Depends, Form, File, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..access import require_owner, Hidden
from ..db import get_session
from ..errors import AppError, RequestInvalid, IdempotencyConflict
from ..models import Actor, ConsentScope, as_utc
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from ..speaker_models import SpeakerRecording
from .. import speaker_identification as recognition
from ..storage.base import checksum_of
from .episodes import _read_upload, _validated_recorded_at

def no_store(response: Response):
    response.headers['Cache-Control'] = 'no-store'

router = APIRouter(prefix='/api/v1/subjects/{subject_id}/speaker-recordings', tags=['speaker-recordings'], dependencies=[Depends(no_store)])
NOTICE = ('点击开始即确认本次录音、云端转写和本段声音识别；原音发送到现用百炼服务。'
          '正常聊天即可，自我介绍可帮助显示姓名，没听清时仍按说话人编号保留文字。'
          '声音不用于登录，不将多人原音整体用于本人音色复刻。')
GUIDE = '自然说一句“我叫小王”就可以，也可以直接开始聊天。'


def own(session, subject_id, rid, actor):
    require_owner(session, subject_id, actor.actor_id)
    row = session.get(SpeakerRecording, rid)
    if row is None or row.subject_id != subject_id or row.actor_id != actor.actor_id:
        raise Hidden('这段多人录音不存在。')
    return row


def view(row):
    return {'recording_id': row.recording_id, 'status': row.status, 'recorded_at': as_utc(row.recorded_at).isoformat(),
        'duration_ms': row.duration_ms, 'consent_id': row.consent_id, 'policy': row.policy,
        'error': row.error, 'report': row.report if row.status == 'ready' else None}


@router.get('/capabilities')
def capabilities(subject_id: str, request: Request, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    settings = request.app.state.settings
    return {'available': recognition.available(settings), 'policy': recognition.policy(settings),
            'notice': NOTICE + (' 清晰自我介绍的声音会在当前人物空间登记声纹，用于以后录音和聊天的辅助识别，可删除或撤销；声音不能替代账号或密码。' if __import__('app.voiceprints',fromlist=['available']).available(settings) else ''), 'introduction_guide': GUIDE, 'identification_scope': 'recording', 'consent_action':'start_recording', 'introduction_optional':True,'voiceprint_available':__import__('app.voiceprints',fromlist=['available']).available(settings)}


class ProcessInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    policy: str = Field(min_length=1, max_length=128)
    accept_current_policy: bool = False


@router.post('')
def capture(subject_id: str, request: Request, response: Response,
            consent_id: str = Form(...), policy: str = Form(...), idempotency_key: str = Form(...),
            recorded_at: datetime = Form(...), duration_ms: int = Form(...), speaker_count: int | None = Form(None),
            participant_consents_confirmed: bool = Form(...), file: UploadFile = File(...),
            actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    settings = request.app.state.settings
    if not recognition.available(settings): raise RequestInvalid('当前服务未接通多人识别，原音请保留在手机。')
    if not participant_consents_confirmed: raise RequestInvalid('请通过开始录音操作确认本次录音、转写和声音识别用途。')
    if policy != recognition.policy(settings): raise RequestInvalid('多人识别用途已变化，请重新阅读确认。')
    ConsentRepository(session).require_active(consent_id, subject_id=subject_id,
        scope=ConsentScope.SPEAKER_IDENTIFICATION, actor_id=actor.actor_id)
    if not 1 <= len(idempotency_key) <= 128 or not 5000 <= duration_ms <= 2 * 3600 * 1000:
        raise RequestInvalid('录音编号或时长不符合范围。')
    if speaker_count is not None and speaker_count not in {2,3}: raise RequestInvalid('多人录音人数须为 2 或 3。')
    at = _validated_recorded_at(recorded_at)
    content_type = (file.content_type or '').split(';')[0]
    if content_type not in {'audio/mp4','audio/x-m4a','audio/wav','audio/x-wav','audio/mpeg','audio/flac'}:
        raise RequestInvalid('多人录音格式尚未接通。')
    audio = _read_upload(file, limit_bytes=settings.max_upload_bytes); checksum = checksum_of(audio)
    existing = session.scalar(select(SpeakerRecording).where(SpeakerRecording.subject_id==subject_id,
        SpeakerRecording.actor_id==actor.actor_id, SpeakerRecording.idempotency_key==idempotency_key))
    if existing:
        if (existing.checksum != checksum or existing.speaker_count != speaker_count or existing.duration_ms != duration_ms or existing.policy != policy
                or existing.consent_id != consent_id or existing.content_type != content_type or as_utc(existing.recorded_at) != at):
            raise IdempotencyConflict('同一录音编号已用于另一份内容或用途。')
        return view(existing)
    rid = 'sr_' + uuid4().hex; key = 'speaker-recordings/' + rid + '/original'
    store = request.app.state.object_store
    store.put(key, audio, content_type)
    row = SpeakerRecording(recording_id=rid, subject_id=subject_id, actor_id=actor.actor_id,
        consent_id=consent_id, policy=policy, idempotency_key=idempotency_key, audio_key=key, checksum=checksum,
        content_type=content_type, speaker_count=speaker_count, duration_ms=duration_ms, recorded_at=at)
    session.add(row)
    try: session.commit()
    except IntegrityError:
        session.rollback(); store.delete(key)
        raise IdempotencyConflict('这段录音正在提交，请使用相同编号稍后重试。') from None
    response.status_code = 201
    return view(row)


@router.get('')
def listing(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    rows = session.scalars(select(SpeakerRecording).where(SpeakerRecording.subject_id==subject_id,
        SpeakerRecording.actor_id==actor.actor_id, SpeakerRecording.status!='deleted').order_by(SpeakerRecording.created_at.desc()).limit(200))
    items = []
    for row in rows:
        try:
            if row.status not in {'deleted','revoked'}: recognition.require_active(session, row)
            items.append(view(row))
        except AppError:
            items.append({**view(row), 'status':'revoked', 'report':None})
    return {'items': items}


@router.get('/{recording_id}')
def read(subject_id: str, recording_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    row = own(session, subject_id, recording_id, actor)
    if row.status not in {'deleted','revoked'}: recognition.require_active(session, row)
    return view(row)


@router.post('/{recording_id}/process')
def process(subject_id: str, recording_id: str, body: ProcessInput, request: Request,
            actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    row = own(session, subject_id, recording_id, actor); recognition.require_active(session, row)
    if row.status in {'deleted','revoked'}: raise RequestInvalid('该段录音已删除或撤销。')
    if body.policy == recognition.policy(request.app.state.settings) and body.accept_current_policy and body.policy != row.policy:
        row.policy=body.policy; session.commit()
    if body.policy != recognition.policy(request.app.state.settings) or body.policy != row.policy:
        raise RequestInvalid('多人识别用途已变化，未继续发送原音。')
    if row.status == 'failed':
        row.status='uploaded'; row.attempts=0; row.error=None; session.commit()
    recognition.run_one(request.app.state.database, request.app.state.object_store, request.app.state.settings, recording_id)
    session.expire_all()
    return view(session.get(SpeakerRecording, recording_id))


@router.get('/{recording_id}/audio')
def audio(subject_id: str, recording_id: str, request: Request,
          actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    row = own(session, subject_id, recording_id, actor); recognition.require_active(session, row)
    if row.status in {'deleted','revoked'} or not row.audio_key: raise Hidden('原音不可用。')
    return Response(request.app.state.object_store.get(row.audio_key), media_type=row.content_type,
                    headers={'Cache-Control':'no-store'})


@router.delete('/{recording_id}')
def delete(subject_id: str, recording_id: str, request: Request,
           actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    row = own(session, subject_id, recording_id, actor)
    recognition.discard(session, request.app.state.object_store, row)
    return view(row)
