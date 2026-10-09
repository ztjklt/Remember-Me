"""Subject-scoped evidence search and Twin answers."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AppError
from ..models import (Actor, Consent, ConsentScope, Episode, Evidence,
                      ModelRevision, PersonTrait, TwinAnswer, utcnow)
from ..repositories.consents import ConsentRepository
from ..retrieval import EmbeddingUnavailable, retrieve
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
    return {
        "answer_id": row.answer_id, "subject_id": row.subject_id,
        "question": row.question, "answer": row.answer if row.invalidated_at is None else "相关记忆已变化，请重新提问。",
        "response_type": row.response_type, "confidence": row.confidence,
        "model_version": row.model_version, "person_model_version": row.person_model_version,
        "source_version": row.source_basis,
        "created_at": row.created_at.isoformat(),
        "stale": row.invalidated_at is not None,
        "expression": row.expression if row.invalidated_at is None else None,
        "evidence": [{"evidence_id": source.evidence_id, "excerpt": source.excerpt,
                      "episode_id": source.episode_id, "source_type": source.source_type}
                     for source in sources if source is not None] if row.invalidated_at is None else [],
    }


@router.get("/memory-search")
def search_memories(subject_id: str, q: str, request: Request,
                    actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    ids = visible_episodes(session, subject_id, actor.actor_id)
    basis = source_basis(session, subject_id)
    reader = not is_owner(session, subject_id, actor_id)
    session.commit()
    if not q.strip() or len(q) > 1000:
        return {"items": []}
    try:
        items = retrieve(session, subject_id, q.strip(), request.app.state.embedding_encoder,
                         episode_ids=ids, reader=reader)
        session.commit()
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新搜索。')
    visible_episodes(session, subject_id, actor_id)
    session.commit()
    return {"items": items}


@router.post("/twin/answers")
def ask(subject_id: str, payload: TwinQuestion, request: Request,
        actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    ids = visible_episodes(session, subject_id, actor_id, cloud=True)
    reader = not is_owner(session, subject_id, actor_id)
    if reader:
        ids -= altered_story_ids(session, ids)
    candidates = effective_materials(session, subject_id, ids)
    from ..narrative import visible_records,contextual_sources
    from ..models import NarrativePreference
    from ..profiles import approved_traits
    sources = contextual_sources(session,subject_id,candidates,visible_episode_ids=ids)
    organized = [r for r in visible_records(session,subject_id,actor_id,sources=sources)
                 if r['status']=='confirmed' and r['source_valid']]
    for trait in (approved_traits(session, subject_id) if not reader else []):
        # Conditions and counterexamples need the same permission check as support.
        if not set(trait.evidence_ids+trait.counter_evidence_ids)<=sources.keys(): continue
        for candidate in candidates:
            if set(trait.evidence_ids).intersection(e['evidence_id'] for e in candidate['evidence']):
                candidate['traits'].append(f'本人确认的系统归纳：{trait.statement}；情境：{trait.context}；不得扩展为所有场景的人格。')
    for record in organized:
        if record['kind'] not in {'story','person','observation'}: continue
        for candidate in candidates:
            if set(record['evidence_ids']).intersection(e['evidence_id'] for e in candidate['evidence']):
                candidate['traits'].append('本人审核的故事整理（非原话，以证据为准）：'+record['text'])
    pref=session.get(NarrativePreference,subject_id)
    examples=[{'id':r['id'],'text':r['text']} for r in organized if r['kind']=='style'] if pref and pref.style_enabled else []
    style_over_budget=len(examples)>8 or sum(len(r['text']) for r in examples)>4000
    if sum(map(len,{t for c in candidates for t in c['traits']})) > 24000:
        raise ContextTooLarge('已确认的人物理解超过上下文预算，请拒绝已不适用的候选；没有截断。')
    basis = source_basis(session, subject_id)
    revision = session.get(ModelRevision, subject_id)
    basis_version = revision.version if revision else 0
    session.commit()
    question = payload.question.strip()
    if not question:
        raise TwinNotFound("Question is empty")
    candidate_ids = {row["memory_item_id"] for row in candidates}
    unresolved = set()
    # Explicit temporal revisions travel as context; an unrelated contradiction
    # must not globally block answering facts from the same recording.
    limited = [{"memory_item_id": row["memory_item_id"], "statement": row["statement"],
                "domain": row["domain"], "unresolved": row["memory_item_id"] in unresolved,
                "traits": row["traits"], "graph_facts": row["graph_facts"],
                "evidence": [{"evidence_id": source["evidence_id"], "excerpt": source["excerpt"],
                              "source_type": source["source_type"]}
                             for source in row["evidence"] if source["excerpt"]]}
               for row in candidates]
    # Retrieval may update cached vectors. Release its transaction before the
    # network call so revocation can proceed while DeepSeek is working.
    session.commit()
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    session.commit()
    if not limited:
        result = {"answer": "现有记录还不足以确定。", "response_type": "UNKNOWN",
                  "evidence_ids": [], "confidence": 0, "model_version": "no-evidence"}
    else:
        if request.app.state.settings.ai_backend != "http":
            raise TwinFailed("请先连接真实的 AI Core 服务。")
        try:
            result = request.app.state.twin_client.answer(question, limited)
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
        session.commit()
        # Only this optional pass may degrade; never replace a failed fact answer.
        expression=request.app.state.twin_client.express(result['answer'],examples)
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    valid = {source["evidence_id"]: (source, row) for row in candidates for source in row["evidence"]}
    kind = result.get("response_type")
    cited = result.get("evidence_ids")
    content = result.get("answer")
    confidence = result.get("confidence")
    version = result.get("model_version")
    if (kind not in {"ORIGINAL", "SIMULATION", "UNKNOWN"} or not isinstance(cited, list)
            or not isinstance(content, str) or len(content) > 500
            or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1
            or not isinstance(version, str) or not version or len(version) > 128
            or len(cited) != len(set(cited)) or any(identifier not in valid for identifier in cited)):
        raise TwinFailed("模型回答的证据格式不正确。")
    if kind == "UNKNOWN":
        content, cited, confidence = "现有记录还不足以确定。", [], 0
    elif not cited or not content.strip():
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
        kind, content, cited, confidence = "UNKNOWN", "现有记录有不同说法，还不能确定。", [], 0
    row = TwinAnswer(answer_id="ta_" + uuid4().hex[:16], subject_id=subject_id,
                     actor_id=actor.actor_id, question=question, answer=content,
                     response_type=kind, evidence_ids=cited,
                     memory_item_ids=list({valid[identifier][1]["memory_item_id"] for identifier in cited}),
                     confidence=confidence, model_version=version,
                     person_model_version=basis_version,
                     source_basis=basis,
                     expression=expression,
                     created_at=utcnow())
    session.add(row)
    session.commit()
    return answer_view(session, row)


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
    if row.invalidated_at is None and row.source_basis != source_basis(session,subject_id):
        row.invalidated_at=utcnow()
        session.commit()
    return answer_view(session, row)
