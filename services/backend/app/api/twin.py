"""Subject-scoped evidence search and Twin answers."""

from __future__ import annotations

from uuid import uuid4
from typing import Callable, Literal

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AppError
from ..models import (Actor, Consent, ConsentScope, Episode, Evidence,
                      ModelRevision, PersonTrait, TwinAnswer, utcnow)
from ..repositories.consents import ConsentRepository
from ..twin_basis import from_material_basis, current as answer_basis
from ..retrieval import EmbeddingUnavailable
from ..evidence_rag import prepare, publish_and_select, search_items
from ..security import current_actor
from ..twin_client import TwinUnavailable
from ..stt import SttProvider
from ..access import visible_episodes, is_owner, require_cloud, source_basis, publication_lock, altered_story_ids
from ..materials import effective_materials, ContextTooLarge

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["twin"])


class TwinNotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class TwinFailed(AppError):
    code = "TWIN_UNAVAILABLE"
    http_status = 503


class SourceChanged(AppError):
    code = 'SOURCE_CHANGED'
    http_status = 409


class TwinQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    cloud_consent_id: str = Field(min_length=1)
    conversation_mode: bool = False
    previous_answer_id: str | None = Field(default=None, min_length=1, max_length=64)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)


class RememberMessage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cloud_consent_id: str = Field(min_length=1)
    recording_consent_id: str = Field(min_length=1)
    confirmed: StrictBool

    @field_validator('confirmed')
    @classmethod
    def confirmed_true(cls, value):
        if value is not True: raise ValueError('Owner confirmation is required')
        return value


@router.post("/twin/transcribe-query")
async def transcribe_query(subject_id: str, request: Request,
                           actor: Actor = Depends(current_actor),
                           session: Session = Depends(get_session)) -> dict:
    """Temporary speech-to-text; never create an Episode or Memory."""
    require_subject(session, subject_id, actor)
    from ..cloud_asr import CLOUD_BACKENDS
    if request.app.state.settings.stt_backend not in {"http", *CLOUD_BACKENDS}:
        raise TwinFailed("请先连接真实的中文语音识别服务。")
    cloud = request.app.state.settings.stt_backend in CLOUD_BACKENDS
    if cloud:
        from ..cloud_asr import cloud_policy
        from ..errors import RequestInvalid
        if request.headers.get('X-Cloud-ASR-Policy') != cloud_policy(request.app.state.settings):
            raise RequestInvalid('请明确同意将提问原音发送到当前云端转写服务。')
    audio = await request.body()
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise TwinFailed("提问录音为空或过大。")
    provider: SttProvider = request.app.state.stt_provider
    try:
        mime = request.headers.get('Content-Type', 'audio/mp4')
        if cloud:
            def authorize():
                with request.app.state.database.session() as guard:
                    require_subject(guard, subject_id, actor)
            transcript = await run_in_threadpool(provider.transcribe_authorized, audio, mime, authorize)
        else:
            transcript = await run_in_threadpool(provider.transcribe, audio, mime)
    except AppError as exc:
        raise TwinFailed("提问录音暂时无法识别，可直接输入问题。") from exc
    from ..chinese_text import simplified_transcript
    return {"text": simplified_transcript(transcript.text), "stt_model_version": transcript.model_version}


def require_subject(session: Session, subject_id: str, actor: Actor) -> None:
    from ..access import require_owner
    require_owner(session, subject_id, actor.actor_id)
    grant = session.scalar(select(Consent).where(
        Consent.subject_id == subject_id, Consent.granted_by_actor_id == actor.actor_id,
        Consent.scope == str(ConsentScope.RECORDING), Consent.status == "granted",
        Consent.revoked_at.is_(None),
    ))
    if grant is None:
        raise TwinNotFound("Subject not found")


def answer_view(session: Session, row: TwinAnswer) -> dict:
    sources = [session.get(Evidence, identifier) for identifier in row.evidence_ids]
    remembered = session.scalar(select(Episode).where(Episode.subject_id == row.subject_id,
        Episode.actor_id == row.actor_id, Episode.idempotency_key == 'chat:' + row.answer_id))
    return {
        "answer_id": row.answer_id, "subject_id": row.subject_id,
        "question": row.question, "answer": row.answer if row.invalidated_at is None else "回答依据或核对规则已更新，请重新提问。",
        "response_type": row.response_type, "confidence": row.confidence,
        "model_version": row.model_version, "person_model_version": row.person_model_version,
        "source_version": row.source_basis,
        "created_at": row.created_at.isoformat(),
        "stale": row.invalidated_at is not None,
        "conversation_id": row.conversation_id,
        "parent_answer_id": row.parent_answer_id,
        "context_turn_count": len(row.context_answer_ids or []),
        "context_truncated": row.context_truncated,
        "recalled_turn_count": len(row.recalled_answer_ids or []) if row.invalidated_at is None else 0,
        "history_summary_status": row.history_summary_status,
        "recalled_answer_ids": (row.recalled_answer_ids or []) if row.invalidated_at is None else [],
        "remembered_episode_id": remembered.episode_id if remembered else None,
        "expression": row.expression if row.invalidated_at is None else None,
        "evidence": [{"evidence_id": source.evidence_id, "excerpt": source.excerpt,
                      "episode_id": source.episode_id, "source_type": source.source_type,
                      "has_audio": bool(session.get(Episode, source.episode_id).audio_object_key)}
                     for source in sources if source is not None] if row.invalidated_at is None else [],
    }


@router.get("/memory-search")
def search_memories(subject_id: str, q: str, request: Request,
                    actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    ids = visible_episodes(session, subject_id, actor.actor_id)
    reader = not is_owner(session, subject_id, actor_id)
    if reader: ids -= altered_story_ids(session, ids)
    candidates = effective_materials(session, subject_id, ids, enforce_budget=False)
    basis = source_basis(session, subject_id)
    session.commit()
    if not q.strip() or len(q) > 1000:
        return {"items": []}
    try:
        plan = prepare(session, subject_id, q.strip(), candidates, request.app.state.embedding_encoder)
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新搜索。')
    visible_episodes(session, subject_id, actor_id)
    items = search_items(publish_and_select(session, plan, candidates))
    session.commit()
    return {"items": items}


@router.post("/twin/answers")
def ask(subject_id: str, payload: TwinQuestion, request: Request,
        actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    return answer_question(subject_id,payload,request,actor,session,chat_history_scope='actor')


def answer_question(subject_id: str, payload: TwinQuestion, request: Request,
                    actor: Actor, session: Session, *, chat_history_scope: Literal['actor','conversation'],
                    publication_guard: Callable[[Session], None] | None = None) -> dict:
    """Internal caller scope; clients cannot opt a voice call into old chats.

    Text keeps historical-chat capability across sessions. Voice uses its own
    saved chain and older turns from that conversation, plus life evidence.
    """
    if chat_history_scope not in {'actor','conversation'}:
        raise ValueError('Unknown internal chat-history scope')
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    if publication_guard: publication_guard(session)
    if payload.conversation_mode:
        from ..access import require_owner
        require_owner(session, subject_id, actor_id)
    elif payload.previous_answer_id is not None:
        raise SourceChanged('续聊需要启用会话模式。')
    if payload.request_id:
        existing = session.scalar(select(TwinAnswer).where(TwinAnswer.subject_id == subject_id,
            TwinAnswer.actor_id == actor_id, TwinAnswer.request_id == payload.request_id))
        if existing is not None:
            if existing.question != payload.question.strip() or existing.parent_answer_id != payload.previous_answer_id or bool(existing.conversation_id) != payload.conversation_mode:
                raise SourceChanged('重试编号已用于另一条消息，请重新发送。')
            if existing.invalidated_at is not None or existing.source_basis != answer_basis(session, subject_id):
                raise SourceChanged('上次回答的依据已变化，请重新发送。')
            return answer_view(session, existing)
    ids = visible_episodes(session, subject_id, actor_id, cloud=True)
    reader = not is_owner(session, subject_id, actor_id)
    if reader:
        ids -= altered_story_ids(session, ids)
    candidates = effective_materials(session, subject_id, ids, enforce_budget=False)
    related_groups = []
    from ..narrative import visible_records,contextual_sources
    from ..models import NarrativePreference
    from ..profiles import approved_traits
    sources = contextual_sources(session,subject_id,candidates,visible_episode_ids=ids)
    organized = [r for r in visible_records(session,subject_id,actor_id,sources=sources)
                 if r['status']=='confirmed' and r['source_valid']]
    for trait in (approved_traits(session, subject_id) if not reader else []):
        # Conditions and counterexamples need the same permission check as support.
        if not set(trait.evidence_ids+trait.counter_evidence_ids)<=sources.keys(): continue
        related_groups.append(set(trait.evidence_ids+trait.counter_evidence_ids))
        for candidate in candidates:
            if set(trait.evidence_ids).intersection(e['evidence_id'] for e in candidate['evidence']):
                candidate['traits'].append(f'本人确认的系统归纳：{trait.statement}；情境：{trait.context}；不得扩展为所有场景的人格。')
    for record in organized:
        if record['kind'] not in {'story','person','observation'}: continue
        related_groups.append(set(record['evidence_ids']))
        for candidate in candidates:
            if set(record['evidence_ids']).intersection(e['evidence_id'] for e in candidate['evidence']):
                candidate['traits'].append('本人审核的故事整理（非原话，以证据为准）：'+record['text'])
    pref=session.get(NarrativePreference,subject_id)
    examples=[{'id':r['id'],'text':r['text']} for r in organized if r['kind']=='style'] if pref and pref.style_enabled else []
    style_over_budget=len(examples)>8 or sum(len(r['text']) for r in examples)>4000
    from ..twin_context import contextual_evidence
    twin_sources = contextual_evidence(session, sources)
    basis = source_basis(session, subject_id)
    revision = session.get(ModelRevision, subject_id)
    basis_version = revision.version if revision else 0
    from ..twin_conversation import context, retrieval_question
    turns, conversation_id, truncated = context(session, subject_id, actor_id,
        payload.previous_answer_id, from_material_basis(basis)) if payload.conversation_mode else ([], None, False)
    if payload.conversation_mode and conversation_id is None: conversation_id = 'tc_' + uuid4().hex
    history_conversation_id = conversation_id if chat_history_scope == 'conversation' else None
    from .. import chat_memory
    recalled, chat_updates, chat_snapshot = [], [], None
    summary, summary_status = None, None
    if payload.conversation_mode and not reader:
        try:
            recalled, chat_updates, chat_snapshot = chat_memory.prepare(session, subject_id, actor_id,
                from_material_basis(basis), retrieval_question(payload.question, turns), turns, request.app.state.embedding_encoder,
                conversation_id=history_conversation_id)
        except EmbeddingUnavailable as exc:
            raise TwinFailed(str(exc)) from exc
    session.commit()
    question = payload.question.strip()
    if not question:
        raise TwinNotFound("Question is empty")
    try:
        plan = prepare(session, subject_id, retrieval_question(question, turns), candidates, request.app.state.embedding_encoder)
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    if publication_guard: publication_guard(session)
    if not chat_memory.publish(session, subject_id, actor_id, from_material_basis(basis), turns, chat_snapshot, chat_updates,
                               conversation_id=history_conversation_id):
        raise SourceChanged('聊天记忆已变化，请重新提问。')
    candidates = publish_and_select(session, plan, candidates, related_groups=related_groups)
    session.commit()
    unresolved = set()
    # Explicit temporal revisions travel as context; an unrelated contradiction
    # must not globally block answering facts from the same recording.
    limited = [{"memory_item_id": row["memory_item_id"], "statement": row["statement"],
                "domain": row["domain"], "unresolved": row["memory_item_id"] in unresolved,
                "traits": row["traits"], "graph_facts": row["graph_facts"],
                "evidence": [twin_sources[source["evidence_id"]]
                             for source in row["evidence"] if source["excerpt"]]}
               for row in candidates]
    # No source writes or locks are held across the answer-provider call.
    session.commit()
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    session.commit()
    if recalled:
        summary, summary_status = chat_memory.digest(session, subject_id, actor_id, recalled, request.app.state.twin_client)
        publication_lock(session, subject_id)
        if basis != source_basis(session, subject_id) or not chat_memory.valid_recall(session, subject_id, actor_id, from_material_basis(basis), recalled,
                                                                                  conversation_id=history_conversation_id):
            raise SourceChanged('聊天记忆或授权已变化，请重新提问。')
        require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
        if publication_guard: publication_guard(session)
        chat_memory.save_digest(session, subject_id, actor_id, summary)
        session.commit()
    if not limited and not payload.conversation_mode:
        result = {"answer": "这件事，我还没有足够的记录可以确认。", "response_type": "UNKNOWN",
                  "evidence_ids": [], "confidence": 0, "model_version": "no-evidence"}
    else:
        if request.app.state.settings.ai_backend != "http":
            raise TwinFailed("请先连接真实的 AI Core 服务。")
        try:
            dialogue_options = {'conversation_turns':turns, 'conversation_mode':True}
            if recalled: dialogue_options['conversation_recall'] = recalled
            if summary: dialogue_options['conversation_summary'] = summary['summary']
            if examples and not style_over_budget:
                dialogue_options['expression_examples'] = [e['text'] for e in examples]
            result = (request.app.state.twin_client.answer(question, limited, **dialogue_options) if payload.conversation_mode else
                      request.app.state.twin_client.answer(question, limited))
        except TwinUnavailable as exc:
            failure = TwinFailed(str(exc))
            if not exc.retryable:
                failure.code = exc.code
                failure.http_status = 502
            raise failure from exc
    expression=None
    if examples and result.get('response_type')=='SIMULATION' and style_over_budget:
        expression={'status':'unavailable','text':'','model_version':'','prompt_version':'expression-checked-v1',
                    'reason':'表达范例超过8条或4000字，本次仅提供有来源的回答。'}
    elif examples and result.get('response_type')=='SIMULATION':
        publication_lock(session,subject_id)
        if basis!=source_basis(session,subject_id):
            raise SourceChanged('资料或授权已变化，请重新提问。')
        require_cloud(session,subject_id,actor_id,payload.cloud_consent_id)
        if publication_guard: publication_guard(session)
        session.commit()
        # Only this optional pass may degrade; never replace a failed fact answer.
        expression=request.app.state.twin_client.express(result['answer'],examples)
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    if publication_guard: publication_guard(session)
    if recalled and not chat_memory.valid_recall(session, subject_id, actor_id, from_material_basis(basis), recalled,
                                                conversation_id=history_conversation_id):
        raise SourceChanged('聊天记忆已变化，请重新提问。')
    valid = {source["evidence_id"]: (source, row) for row in candidates for source in row["evidence"]}
    kind = result.get("response_type")
    cited = result.get("evidence_ids")
    content = result.get("answer")
    confidence = result.get("confidence")
    version = result.get("model_version")
    allowed_kinds = {"ORIGINAL", "SIMULATION", "UNKNOWN"} | ({"CONVERSATION"} if payload.conversation_mode else set())
    if (kind not in allowed_kinds or not isinstance(cited, list)
            or not isinstance(content, str) or len(content) > 500
            or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1
            or not isinstance(version, str) or not version or len(version) > 128
            or len(cited) != len(set(cited)) or any(identifier not in valid for identifier in cited)):
        raise TwinFailed("模型回答的证据格式不正确。")
    if kind == "UNKNOWN":
        content, cited, confidence = "这件事，我还没有足够的记录可以确认。", [], 0
    elif (kind != 'CONVERSATION' and not cited) or not content.strip():
        raise TwinFailed("模型回答缺少可核对的证据。")
    if kind == "ORIGINAL":
        def verified_original(identifier: str) -> bool:
            source = session.get(Evidence, identifier)
            if (source is None or source.source_type != "SUBJECT" or
                    source.span_start is None or source.span_end is None):
                return False
            episode = session.get(Episode, source.episode_id)
            if episode is None or episode.subject_id != subject_id or not episode.transcript:
                return False
            return (episode.transcript[source.span_start:source.span_end] == source.excerpt
                    and content.strip("“”\"'。 ") == source.excerpt.strip("“”\"'。 "))

        if not any(verified_original(identifier) for identifier in cited):
            raise TwinFailed("模型给出的原话无法在录音转写中定位。")
    if kind == "SIMULATION" and any(valid[identifier][1]["memory_item_id"] in unresolved for identifier in cited):
        kind, content, cited, confidence = "UNKNOWN", "这件事的记录有不同说法，我还不能确认。", [], 0
    if payload.request_id:
        # A concurrent retry may have published while the provider was running.
        existing = session.scalar(select(TwinAnswer).where(TwinAnswer.subject_id == subject_id,
            TwinAnswer.actor_id == actor_id, TwinAnswer.request_id == payload.request_id))
        if existing is not None:
            if existing.question != question or existing.parent_answer_id != payload.previous_answer_id:
                raise SourceChanged('重试编号已用于另一条消息。')
            return answer_view(session, existing)
    row = TwinAnswer(answer_id="ta_" + uuid4().hex[:16], subject_id=subject_id,
                     conversation_id=conversation_id, parent_answer_id=payload.previous_answer_id,
                     request_id=payload.request_id, context_answer_ids=[t['answer_id'] for t in turns],
                     context_truncated=truncated, recalled_answer_ids=[t['answer_id'] for t in recalled],
                     history_summary_status='ready' if summary_status=='generated' else summary_status,
                     actor_id=actor.actor_id, question=question, answer=content,
                     response_type=kind, evidence_ids=cited,
                     memory_item_ids=list({valid[identifier][1]["memory_item_id"] for identifier in cited}),
                     confidence=confidence, model_version=version,
                     person_model_version=basis_version,
                     source_basis=from_material_basis(basis),
                     expression=expression,
                     created_at=utcnow())
    session.add(row)
    session.commit()
    return answer_view(session, row)


@router.post('/twin/answers/{answer_id}/remember', status_code=201)
def remember_message(subject_id: str, answer_id: str, payload: RememberMessage, request: Request,
                     actor: Actor = Depends(current_actor), session: Session = Depends(get_session)):
    from ..access import require_owner
    from ..models import MemoryItem
    from ..repositories.episodes import EpisodeRepository, new_episode_id
    from ..repositories.person_model import PersonModelRepository
    from ..language_support import store_supplement
    from ..retrieval import invalidate_answers
    publication_lock(session, subject_id)
    require_owner(session, subject_id, actor.actor_id)
    require_cloud(session, subject_id, actor.actor_id, payload.cloud_consent_id)
    ConsentRepository(session).require_active(payload.recording_consent_id, subject_id=subject_id,
        actor_id=actor.actor_id, scope=ConsentScope.RECORDING)
    row = session.scalar(select(TwinAnswer).where(TwinAnswer.answer_id == answer_id,
        TwinAnswer.subject_id == subject_id, TwinAnswer.actor_id == actor.actor_id))
    if row is None: raise TwinNotFound('聊天消息不存在。')
    existing = EpisodeRepository(session).find_by_idempotency(subject_id=subject_id,
        actor_id=actor.actor_id, idempotency_key='chat:' + row.answer_id)
    if existing is not None:
        note = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == existing.episode_id))
        if note is None or note.deleted_at is not None or note.review_state != 'active':
            raise SourceChanged('这条文字记忆已经停用，不会自动重新创建。')
        return {'episode_id': existing.episode_id, 'memory_item_id': note.memory_item_id,
                'status': existing.status, 'source': 'IOS_TEXT'}
    now = utcnow()
    episode = Episode(episode_id=new_episode_id(), subject_id=subject_id, actor_id=actor.actor_id,
        recording_consent_id=payload.recording_consent_id, idempotency_key='chat:' + row.answer_id,
        source='IOS_TEXT', recorded_at=row.created_at, duration_ms=None,
        capture_metadata={'origin':'confirmed_chat_message','twin_answer_id':row.answer_id,
                          'conversation_id':row.conversation_id,'review_supplement':row.question},
        audio_ref=None, audio_object_key=None, audio_size_bytes=0,
        audio_content_type='text/plain', audio_checksum=None,
        status='ready', trace_id='text_' + uuid4().hex,
        transcript=row.question, stt_transcript=None, transcript_reviewed_at=now,
        transcript_reviewed_by=actor.actor_id, stt_backend='owner-text', stt_model_version='owner-text-v1',
        model_version='owner-input', created_at=now, updated_at=now)
    session.add(episode); session.flush()
    store_supplement(session, episode)
    PersonModelRepository(session).rebuild(subject_id, include_episode_id=episode.episode_id)
    invalidate_answers(session, request.app.state.object_store, subject_id)
    note = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == episode.episode_id))
    session.commit()
    return {'episode_id':episode.episode_id, 'memory_item_id':note.memory_item_id,
            'status':'ready', 'source':'IOS_TEXT'}


@router.get("/twin/answers/{answer_id}")
def read_answer(subject_id: str, answer_id: str,
                actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id=actor.actor_id
    publication_lock(session,subject_id)
    visible_episodes(session, subject_id, actor_id)
    row = session.scalar(select(TwinAnswer).where(
        TwinAnswer.answer_id == answer_id, TwinAnswer.subject_id == subject_id,
        TwinAnswer.actor_id == actor.actor_id))
    if row is None:
        raise TwinNotFound("Answer not found")
    if row.conversation_id:
        grant = session.scalar(select(Consent).where(Consent.subject_id == subject_id,
            Consent.granted_by_actor_id == actor_id, Consent.scope == str(ConsentScope.CLOUD_TWIN),
            Consent.status == 'granted', Consent.revoked_at.is_(None)))
        if grant is None: raise TwinNotFound('会话授权已撤销。')
    if row.invalidated_at is None and row.source_basis != answer_basis(session,subject_id):
        row.invalidated_at=utcnow()
        session.commit()
    return answer_view(session, row)


class ChatMemoryPreference(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool


def _chat_memory_view(session, subject_id, actor_id, basis):
    from .. import chat_memory
    from ..models import ChatDigest
    pref = chat_memory.state(session, subject_id, actor_id)
    turns = chat_memory.history(session, subject_id, actor_id, basis)
    by_id = {t['answer_id']:t for t in turns}
    summaries = []
    for item in session.scalars(select(ChatDigest).where(ChatDigest.subject_id==subject_id,
        ChatDigest.actor_id==actor_id).order_by(ChatDigest.created_at.desc()).limit(100)):
        originals = [by_id[id] for id in item.source_answer_ids if id in by_id]
        if len(originals)==len(item.source_answer_ids) and chat_memory.fingerprint(originals)==item.source_hash:
            summaries.append(dict(summary=item.summary, source_answer_ids=item.source_answer_ids,
                model_version=item.model_version, created_at=item.created_at.isoformat()))
    return dict(enabled=pref.enabled if pref else True, available_turn_count=len(turns),
        forgotten_before=pref.forgotten_before.isoformat() if pref and pref.forgotten_before else None,
        items=list(reversed(turns))[:50], summaries=summaries[:10])


@router.get('/twin/chat-memory')
def read_chat_memory(subject_id: str, request: Request, cloud_consent_id: str, q: str='', answer_ids: str='',
                     actor: Actor=Depends(current_actor), session: Session=Depends(get_session)):
    from ..access import require_owner
    from .. import chat_memory
    require_owner(session,subject_id,actor.actor_id)
    require_cloud(session,subject_id,actor.actor_id,cloud_consent_id)
    basis=source_basis(session,subject_id)
    view=_chat_memory_view(session,subject_id,actor.actor_id,from_material_basis(basis))
    if answer_ids:
        ids=set(answer_ids.split(','))
        if len(ids)>12: raise TwinFailed('来源数量过多。')
        view['items']=[t for t in chat_memory.history(session,subject_id,actor.actor_id,from_material_basis(basis)) if t['answer_id'] in ids]
    elif q.strip():
        if len(q)>1000: raise TwinFailed('搜索内容过长。')
        selected,updates,snapshot=chat_memory.prepare(session,subject_id,actor.actor_id,
            from_material_basis(basis),q.strip(),[],request.app.state.embedding_encoder)
        publication_lock(session,subject_id)
        if basis!=source_basis(session,subject_id) or not chat_memory.publish(session,subject_id,actor.actor_id,from_material_basis(basis),[],snapshot,updates):
            raise SourceChanged('聊天记忆已变化，请重新搜索。')
        require_cloud(session,subject_id,actor.actor_id,cloud_consent_id)
        session.commit()
        view['items']=list(reversed(selected))
    return view


@router.put('/twin/chat-memory')
def configure_chat_memory(subject_id: str, body: ChatMemoryPreference, request: Request,
                          actor: Actor=Depends(current_actor), session: Session=Depends(get_session)):
    from ..access import require_owner
    from ..models import ChatMemoryState
    from .. import chat_memory
    from ..retrieval import invalidate_answers
    publication_lock(session,subject_id); require_owner(session,subject_id,actor.actor_id)
    pref=chat_memory.state(session,subject_id,actor.actor_id)
    if pref is None:
        pref=ChatMemoryState(subject_id=subject_id,actor_id=actor.actor_id,enabled=body.enabled,revision=0)
        session.add(pref)
    if pref.enabled!=body.enabled:
        pref.enabled=body.enabled;pref.revision+=1
    session.flush()
    invalidate_answers(session,request.app.state.object_store,subject_id)
    session.commit()
    return {'enabled':pref.enabled}


@router.delete('/twin/chat-memory')
def clear_chat_memory(subject_id: str, request: Request, actor: Actor=Depends(current_actor),
                      session: Session=Depends(get_session)):
    from ..access import require_owner
    from .. import chat_memory
    from ..retrieval import invalidate_answers
    publication_lock(session,subject_id);require_owner(session,subject_id,actor.actor_id)
    pref=chat_memory.clear(session,subject_id,actor.actor_id)
    session.flush()
    invalidate_answers(session,request.app.state.object_store,subject_id)
    session.commit()
    return {'enabled':pref.enabled,'available_turn_count':0,'forgotten_before':pref.forgotten_before.isoformat(),
            'items':[],'summaries':[]}
