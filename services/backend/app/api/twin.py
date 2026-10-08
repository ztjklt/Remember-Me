"""Subject-scoped evidence search and Twin answers."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
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

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["twin"])


class TwinNotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class TwinFailed(AppError):
    code = "TWIN_UNAVAILABLE"
    http_status = 503


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
    if request.app.state.settings.stt_backend != "http":
        raise TwinFailed("请先连接真实的中文语音识别服务。")
    audio = await request.body()
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise TwinFailed("提问录音为空或过大。")
    provider: SttProvider = request.app.state.stt_provider
    try:
        transcript = await run_in_threadpool(provider.transcribe, audio, "audio/mp4")
    except AppError as exc:
        raise TwinFailed("提问录音暂时无法识别，可直接输入问题。") from exc
    return {"text": transcript.text, "stt_model_version": transcript.model_version}


def require_subject(session: Session, subject_id: str, actor: Actor) -> None:
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
        "created_at": row.created_at.isoformat(),
        "stale": row.invalidated_at is not None,
        "evidence": [{"evidence_id": source.evidence_id, "excerpt": source.excerpt,
                      "episode_id": source.episode_id, "source_type": source.source_type}
                     for source in sources if source is not None] if row.invalidated_at is None else [],
    }


@router.get("/memory-search")
def search_memories(subject_id: str, q: str, request: Request,
                    actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    if not q.strip() or len(q) > 1000:
        return {"items": []}
    try:
        items = retrieve(session, subject_id, q.strip(), request.app.state.embedding_encoder)
        session.commit()
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    return {"items": items}


@router.post("/twin/answers")
def ask(subject_id: str, payload: TwinQuestion, request: Request,
        actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(payload.cloud_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.CLOUD_TWIN, actor_id=actor.actor_id)
    question = payload.question.strip()
    if not question:
        raise TwinNotFound("Question is empty")
    try:
        candidates = retrieve(session, subject_id, question, request.app.state.embedding_encoder)
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    candidate_ids = {row["memory_item_id"] for row in candidates}
    unresolved = set()
    for trait in session.scalars(select(PersonTrait).where(
        PersonTrait.subject_id == subject_id, PersonTrait.status == "unresolved")):
        unresolved.update(set(trait.memory_item_ids or []).intersection(candidate_ids))
    limited = [{"memory_item_id": row["memory_item_id"], "statement": row["statement"],
                "domain": row["domain"], "unresolved": row["memory_item_id"] in unresolved,
                "traits": row["traits"], "graph_facts": row["graph_facts"],
                "evidence": [{"evidence_id": source["evidence_id"], "excerpt": source["excerpt"],
                              "source_type": source["source_type"]}
                             for source in row["evidence"] if source["excerpt"]]}
               for row in candidates]
    baseline = session.get(ModelRevision, subject_id)
    baseline_version = baseline.version if baseline else 0
    # Retrieval may update cached vectors. Release its transaction before the
    # network call so revocation can proceed while DeepSeek is working.
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
            raise TwinFailed(str(exc)) from exc
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
    session.commit()
    session.expire_all()
    ConsentRepository(session).require_active(payload.cloud_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.CLOUD_TWIN, actor_id=actor.actor_id)
    revision = session.get(ModelRevision, subject_id)
    if revision is not None:
        held = session.execute(update(ModelRevision).where(
            ModelRevision.subject_id == subject_id, ModelRevision.version == baseline_version
        ).values(version=ModelRevision.version), execution_options={"synchronize_session": False})
        if held.rowcount != 1:
            session.rollback()
            raise TwinFailed("记忆与画像在回答期间已更新，请重新提问。")
    elif baseline_version:
        raise TwinFailed("画像已更新，请重新提问。")
    row = TwinAnswer(answer_id="ta_" + uuid4().hex[:16], subject_id=subject_id,
                     actor_id=actor.actor_id, question=question, answer=content,
                     response_type=kind, evidence_ids=cited,
                     memory_item_ids=list({valid[identifier][1]["memory_item_id"] for identifier in cited}),
                     confidence=confidence, model_version=version,
                     person_model_version=baseline_version,
                     created_at=utcnow())
    session.add(row)
    session.commit()
    return answer_view(session, row)


@router.get("/twin/answers/{answer_id}")
def read_answer(subject_id: str, answer_id: str,
                actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    row = session.scalar(select(TwinAnswer).where(
        TwinAnswer.answer_id == answer_id, TwinAnswer.subject_id == subject_id,
        TwinAnswer.actor_id == actor.actor_id))
    if row is None:
        raise TwinNotFound("Answer not found")
    return answer_view(session, row)
