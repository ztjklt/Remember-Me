"""Local real-data workbench. All APIs remain authenticated and subject scoped."""
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import Hidden, is_owner, require_owner, visible_episodes, publication_lock, altered_story_ids
from ..db import get_session
from ..errors import RequestInvalid
from ..models import (Actor, Subject, Episode, MemoryItem, Evidence, StoryGrant,
                      MemoryRevision, QuestionRequest, CaptureQuestion, Consent, ModelRevision, Job, utcnow, as_utc)
from ..security import current_actor
from ..chinese_text import simplified_transcript
from ..retrieval import invalidate_answers
from ..repositories.person_model import PersonModelRepository

router = APIRouter(prefix='/api/v1/workbench', tags=['agent-workbench'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class VocabularyInput(Strict):
    text: str = Field(max_length=3000)


@router.get('/subjects/{subject_id}/vocabulary')
def vocabulary(subject_id: str, actor=Depends(current_actor), session=Depends(get_session)):
    from ..models import SubjectVocabulary
    require_owner(session,subject_id,actor.actor_id)
    row=session.get(SubjectVocabulary,subject_id)
    return {'text': row.text if row else '', 'scope':'owner', 'automatic_model_use':False}


@router.put('/subjects/{subject_id}/vocabulary')
def save_vocabulary(subject_id: str, body:VocabularyInput, actor=Depends(current_actor), session=Depends(get_session)):
    from ..models import SubjectVocabulary
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    row=session.get(SubjectVocabulary,subject_id)
    if row is None:
        row=SubjectVocabulary(subject_id=subject_id,text=body.text);session.add(row)
    else: row.text=body.text;row.updated_at=utcnow()
    session.commit()
    return {'text':row.text,'scope':'owner','automatic_model_use':False}


class GrantInput(Strict):
    episode_id: str
    reader_actor_id: str
    include_audio_confirmed: Literal[True]
    cloud_processing_allowed: bool = False


class RevisionInput(Strict):
    target_memory_id: str
    episode_id: str
    kind: Literal['supplement', 'correction', 'change']
    time_text: str | None = Field(default=None, max_length=200)


class RequestInput(Strict):
    text: str = Field(min_length=1, max_length=1000)


class RequestUpdate(Strict):
    status: Literal['pending', 'snoozed', 'declined', 'answered']
    answer_episode_id: str | None = None


def view(row):
    from datetime import datetime
    from ..models import as_utc
    return {column.name: as_utc(value).isoformat() if isinstance(value, datetime) else value
            for column in row.__table__.columns for value in [getattr(row, column.name)]}


def own_episode(session, subject_id, episode_id, actor):
    require_owner(session, subject_id, actor.actor_id)
    episode = session.get(Episode, episode_id)
    if episode is None or episode.subject_id != subject_id:
        raise Hidden('故事不存在。')
    return episode


@router.get('/spaces')
def spaces(actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    owned = list(session.scalars(select(Subject).where(Subject.owner_actor_id == actor.actor_id)))
    shared_ids = select(Episode.subject_id).join(StoryGrant).where(
        StoryGrant.reader_actor_id == actor.actor_id, StoryGrant.revoked_at.is_(None))
    shared = list(session.scalars(select(Subject).where(Subject.subject_id.in_(shared_ids),
        Subject.owner_actor_id.is_not(None), Subject.owner_actor_id != actor.actor_id)))
    return {'actor_id': actor.actor_id, 'display_name': actor.display_name,
        'items': [{'subject_id': s.subject_id, 'display_name': s.display_name, 'role': role}
                  for rows, role in [(owned, 'owner'), (shared, 'reader')] for s in rows]}


@router.get('/capabilities')
def capabilities(request: Request, actor: Actor = Depends(current_actor)):
    settings = request.app.state.settings
    from ..cloud_asr import cloud_policy, configured, destination, CLOUD_BACKENDS
    cloud = settings.stt_backend in CLOUD_BACKENDS
    available=False
    if settings.ai_backend=='http':
        import httpx
        try:
            health=httpx.get(settings.ai_core_url.rstrip('/')+'/health',timeout=1,trust_env=False,follow_redirects=False)
            available=health.is_success
        except httpx.HTTPError:
            pass
    return {'stt': settings.stt_backend, 'ai': settings.ai_backend,
        'live_configured': settings.stt_backend in {'http', *CLOUD_BACKENDS} and settings.ai_backend == 'http',
        'client_transcript_upload': True,
        'client_transcript_endpoint': '/api/v1/episodes/client-transcribed',
        'stt_processing': 'client' if settings.stt_backend == 'client' else ('cloud' if cloud else ('test' if settings.stt_backend == 'fake' else 'http')),
        'stt_configured': configured(settings) if cloud else settings.stt_backend == 'http',
        'cloud_asr_policy': cloud_policy(settings) if cloud else None,
        'stt_model': destination(settings)['model'] if cloud else None,
        'stt_host': destination(settings)['host'] if cloud else None,
        'ai_available':available,
        'notice': ('本服务接收客户端机器转写，等待本人核对；客户端转写是否可用需在该设备实际验证。'
                   if settings.stt_backend == 'client' else '配置不等于服务可用；实际结果保留模型版本。'),
        'schema_version': '0.6.0', 'audio_alignment': False, 'narrative': True}


@router.get('/subjects/{subject_id}/stories')
def stories(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    ids = visible_episodes(session, subject_id, actor.actor_id)
    owner = is_owner(session, subject_id, actor.actor_id)
    altered = altered_story_ids(session, ids) if not owner else set()
    items = []
    for episode in session.scalars(select(Episode).where(Episode.episode_id.in_(ids)).order_by(Episode.recorded_at.desc())):
        job = session.scalar(select(Job).where(Job.episode_id == episode.episode_id)) if owner else None
        memory_rows = list(session.scalars(select(MemoryItem).where(
            MemoryItem.episode_id == episode.episode_id, MemoryItem.deleted_at.is_(None))))
        active = [m for m in memory_rows if m.review_state == 'active']
        # A corrected private replacement must not leak via a formerly shared
        # transcript or original-audio endpoint. The owner retains the history.
        unavailable = episode.episode_id in altered
        values = []
        for memory in (memory_rows if owner else active):
            if unavailable:
                break
            sources = [session.get(Evidence, eid) for eid in memory.evidence_ids]
            values.append({'memory_item_id': memory.memory_item_id, 'content': memory.content,
                'memory_type': memory.memory_type, 'review_state': memory.review_state,
                'domain': (memory.item_metadata or {}).get('domain'),
                'source_type': memory.source_type,
                'origin': (memory.item_metadata or {}).get('origin', 'extracted'),
                'evidence': [{'evidence_id': e.evidence_id, 'excerpt': e.excerpt,
                    'source_type': e.source_type, 'episode_id': e.episode_id} for e in sources
                    if e is not None and e.episode_id == episode.episode_id]})
        items.append({'episode_id': episode.episode_id, 'status': episode.status,
            'recorded_at': as_utc(episode.recorded_at).isoformat(), 'duration_ms': episode.duration_ms,
            'transcript': None if unavailable else (simplified_transcript(episode.transcript)
                if episode.transcript is not None and episode.transcript_reviewed_at is None else episode.transcript),
            'machine_transcript': episode.stt_transcript if owner else None,
            'reviewed': episode.transcript_reviewed_at is not None,
            'waiting_for_review': bool(job and job.state == 'waiting'),
            'can_reextract_empty': bool(owner and episode.status == 'ready' and episode.transcript_reviewed_at
                and session.scalar(select(MemoryItem.memory_item_id).where(MemoryItem.episode_id == episode.episode_id).limit(1)) is None),
            'model_version': episode.model_version, 'stt_model_version': episode.stt_model_version,
            'error_code': episode.error_code, 'error_message': episode.error_message,
            'unavailable': unavailable, 'memories': values,
            'notice': '相关内容已更新，当前不可用。' if unavailable else None})
    return {'subject_id': subject_id, 'role': 'owner' if owner else 'reader', 'items': items}


@router.get('/subjects/{subject_id}/stories/{episode_id}/audio')
def audio(subject_id: str, episode_id: str, request: Request,
          actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    if episode_id not in visible_episodes(session, subject_id, actor.actor_id):
        raise Hidden('原音不可用。')
    episode = session.get(Episode, episode_id)
    if not is_owner(session, subject_id, actor.actor_id):
        if altered_story_ids(session, {episode_id}):
            raise Hidden('相关内容已更新，当前不可用。')
    return Response(request.app.state.object_store.get(episode.audio_object_key),
                    media_type=episode.audio_content_type, headers={'Cache-Control': 'private, no-store'})


@router.post('/subjects/{subject_id}/grants', status_code=201)
def grant(subject_id: str, body: GrantInput, request: Request,
          actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    publication_lock(session, subject_id)
    episode = own_episode(session, subject_id, body.episode_id, actor)
    if episode.status != 'ready' or episode.transcript_reviewed_at is None:
        raise RequestInvalid('请先核对文字并完成整理。')
    if body.reader_actor_id == actor.actor_id or session.get(Actor, body.reader_actor_id) is None:
        raise RequestInvalid('请提供另一个已创建的读者身份。')
    if altered_story_ids(session, {body.episode_id}):
        raise RequestInvalid('请先处理这个故事的修订。')
    previous = session.scalar(select(StoryGrant).where(StoryGrant.episode_id == body.episode_id,
        StoryGrant.reader_actor_id == body.reader_actor_id, StoryGrant.revoked_at.is_(None)))
    if previous:
        if bool(previous.cloud_processing_allowed) != body.cloud_processing_allowed:
            raise RequestInvalid('变更分享范围前，请先撤销旧授权。')
        return view(previous)
    row = StoryGrant(grant_id='grant_' + uuid4().hex[:16], episode_id=body.episode_id,
                    reader_actor_id=body.reader_actor_id, cloud_processing_allowed=int(body.cloud_processing_allowed))
    session.add(row)
    invalidate_answers(session, request.app.state.object_store, subject_id)
    session.commit()
    return view(row)


@router.get('/subjects/{subject_id}/grants')
def grants(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    ids = visible_episodes(session, subject_id, actor.actor_id)
    query = select(StoryGrant).where(StoryGrant.episode_id.in_(ids), StoryGrant.revoked_at.is_(None))
    if not is_owner(session, subject_id, actor.actor_id):
        query = query.where(StoryGrant.reader_actor_id == actor.actor_id)
    return {'items': [view(row) for row in session.scalars(query)]}


@router.delete('/subjects/{subject_id}/grants/{grant_id}')
def revoke(subject_id: str, grant_id: str, request: Request,
           actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    publication_lock(session, subject_id)
    require_owner(session, subject_id, actor.actor_id)
    row = session.get(StoryGrant, grant_id)
    if row is None:
        raise Hidden('授权不存在。')
    own_episode(session, subject_id, row.episode_id, actor)
    row.revoked_at = row.revoked_at or utcnow()
    invalidate_answers(session, request.app.state.object_store, subject_id)
    session.commit()
    return {'revoked': True}


@router.post('/subjects/{subject_id}/revisions', status_code=201)
def propose_revision(subject_id: str, body: RevisionInput, request: Request,
                     actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    publication_lock(session, subject_id)
    episode = own_episode(session, subject_id, body.episode_id, actor)
    target = session.get(MemoryItem, body.target_memory_id)
    if target is None or target.deleted_at is not None or target.review_state != 'active':
        raise Hidden('待修改记忆不存在。')
    own_episode(session, subject_id, target.episode_id, actor)
    if target.episode_id == body.episode_id:
        raise RequestInvalid('请使用一段新的录音补充或纠正。')
    if body.kind == 'change' and not body.time_text:
        raise RequestInvalid('请说明变化发生的大致时间；不确定时可以填写“后来，具体时间不确定”。')
    previous = session.scalar(select(MemoryRevision).where(MemoryRevision.episode_id == body.episode_id))
    if previous:
        if (previous.target_memory_id, previous.kind, previous.time_text) != (body.target_memory_id, body.kind, body.time_text):
            raise RequestInvalid('这段录音已经关联另一项修订。')
        return view(previous)
    if (episode.transcript_reviewed_at is not None or episode.status not in {'uploaded', 'transcribing'}
            or episode.source not in {'IMPORT', 'IOS_MIC', 'ANDROID_MIC'}):
        raise RequestInvalid('请在确认转写前关联修订，避免已公开的结果被重新解释。')
    row = MemoryRevision(revision_id='rev_' + uuid4().hex[:16], subject_id=subject_id,
        target_memory_id=body.target_memory_id, episode_id=body.episode_id, kind=body.kind, time_text=body.time_text)
    session.add(row)
    session.commit()
    return view(row)


@router.get('/subjects/{subject_id}/revisions')
def revisions(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    return {'items': [view(row) for row in session.scalars(select(MemoryRevision).where(MemoryRevision.subject_id == subject_id))]}


@router.post('/subjects/{subject_id}/revisions/{revision_id}/confirm')
def confirm_revision(subject_id: str, revision_id: str, request: Request,
                     actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    publication_lock(session, subject_id)
    require_owner(session, subject_id, actor.actor_id)
    row = session.get(MemoryRevision, revision_id)
    if row is None or row.subject_id != subject_id:
        raise Hidden('修订不存在。')
    if row.status == 'confirmed':
        return view(row)
    episode = own_episode(session, subject_id, row.episode_id, actor)
    if episode.status != 'ready':
        raise RequestInvalid('请等待新录音整理完成，再核对修订。')
    target = session.get(MemoryItem, row.target_memory_id)
    if target.deleted_at is not None or target.review_state != 'active':
        raise RequestInvalid('原记忆已变化，请重新核对。')
    memories = list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id == row.episode_id,
                                                            MemoryItem.deleted_at.is_(None))))
    if not memories:
        raise RequestInvalid('新录音尚无可确认的记忆。')
    if row.kind == 'correction':
        target.review_state = 'superseded'
    for memory in memories:
        memory.review_state = 'active'
        memory.item_metadata = {**(memory.item_metadata or {}), 'relation_kind': row.kind,
            'time_context': row.time_text, 'previous_memory_id': row.target_memory_id}
    row.status, row.confirmed_at = 'confirmed', utcnow()
    PersonModelRepository(session).rebuild(subject_id)
    invalidate_answers(session, request.app.state.object_store, subject_id)
    session.commit()
    return view(row)


@router.post('/subjects/{subject_id}/requests', status_code=201)
def create_request(subject_id: str, body: RequestInput,
                   actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    visible_episodes(session, subject_id, actor.actor_id)
    row = QuestionRequest(request_id='qr_' + uuid4().hex[:16], subject_id=subject_id,
                          actor_id=actor.actor_id, text=body.text)
    session.add(row)
    session.commit()
    return view(row)


@router.get('/subjects/{subject_id}/requests')
def requests(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    ids = visible_episodes(session, subject_id, actor.actor_id)
    owner = is_owner(session, subject_id, actor.actor_id)
    query = select(QuestionRequest).where(QuestionRequest.subject_id == subject_id)
    if not owner:
        query = query.where(QuestionRequest.actor_id == actor.actor_id)
    items = []
    for row in session.scalars(query.order_by(QuestionRequest.created_at.desc())):
        value = view(row)
        if not owner and row.answer_episode_id not in ids:
            value['answer_episode_id'] = None
        items.append(value)
    return {'items': items}


@router.patch('/subjects/{subject_id}/requests/{request_id}')
def update_request(subject_id: str, request_id: str, body: RequestUpdate,
                   actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    row = session.get(QuestionRequest, request_id)
    if row is None or row.subject_id != subject_id:
        raise Hidden('问题不存在。')
    if body.status == 'answered':
        if not body.answer_episode_id:
            raise RequestInvalid('请选择本人已核对的回答录音。')
        episode = own_episode(session, subject_id, body.answer_episode_id, actor)
        if episode.status != 'ready' or episode.transcript_reviewed_at is None:
            raise RequestInvalid('回答尚未完成核对和整理。')
    row.status, row.answer_episode_id = body.status, body.answer_episode_id if body.status == 'answered' else None
    session.commit()
    return view(row)


@router.patch('/subjects/{subject_id}/questions/{question_id}')
def dismiss_prompt(subject_id: str, question_id: str, body: RequestUpdate,
                   actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    row = session.get(CaptureQuestion, question_id)
    if row is None or row.subject_id != subject_id:
        raise Hidden('建议问题不存在。')
    if body.status not in {'snoozed', 'declined', 'pending'}:
        raise RequestInvalid('问题回答必须关联实际录音。')
    row.status = 'skipped' if body.status == 'declined' else body.status
    session.commit()
    return {'question_id': question_id, 'status': row.status}


@router.get('/subjects/{subject_id}/portrait')
def portrait(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    from ..materials import effective_materials, ContextTooLarge
    publication_lock(session,subject_id)
    data = stories(subject_id, actor, session)
    groups = {key: [] for key in ['人生经历', '重要的人', '在意与选择', '说话与表达']}
    unavailable=[]
    seen_sources=set()
    for story in data['items']:
        if story['status'] != 'ready' or story['unavailable']:
            continue
        # Active siblings may share an excerpt with a now-invalid fact. Reuse
        # the answer resolver instead of resurrecting raw text in current views.
        try:
            effective=effective_materials(session,subject_id,{story['episode_id']})
        except ContextTooLarge:
            unavailable.append(story['episode_id'])
            continue
        by_id={m['memory_item_id']:m for m in effective}
        for memory in story['memories']:
            current=by_id.get(memory['memory_item_id'])
            if memory['review_state'] != 'active' or current is None:
                continue
            category = ('重要的人' if memory['memory_type'] in {'PERSON', 'RELATIONSHIP'} else
                        '在意与选择' if memory['memory_type'] in {'VALUE', 'PREFERENCE'} else '人生经历')
            groups[category].append({**memory, 'evidence':current['evidence'], 'episode_id': story['episode_id'], 'label': '本人书面补充，不是录音原话' if memory['origin']=='owner_supplement' else '系统整理，依据本次讲述'})
            for evidence in current['evidence']:
                if evidence['source_type'] == 'SUBJECT' and evidence['evidence_id'] not in seen_sources:
                    seen_sources.add(evidence['evidence_id'])
                    groups['说话与表达'].append({**evidence, 'content': evidence['excerpt'], 'label': '核对文字中的原话'})
    version = session.get(ModelRevision, subject_id)
    import hashlib,json
    visible_version=hashlib.sha256(json.dumps(groups,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    version_number=version.version if version else 0
    session.commit()
    return {'subject_id': subject_id, 'version': version_number,
            'source_version':visible_version,
            'scope': 'owner' if data['role'] == 'owner' else 'shared_stories_only', 'views': groups,
            'unavailable_episode_ids':unavailable,
            'notice': '按可见证据组织，不代表稳定人格或完整人物画像。'+('部分故事过长，暂未在人物视图展开，可回故事查阅。' if unavailable else '')}
