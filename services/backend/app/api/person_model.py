"""Single-subject memory, evidence, profile, questions, and calibration API."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AppError
from ..models import (
    Actor, CaptureQuestion, Consent, Episode, Evidence, GraphFact, MemoryAudit,
    MemoryItem, MemoryEmbedding, ModelRevision, PERSON_DOMAINS, PersonTrait, as_utc, utcnow,
)
from ..repositories.person_model import PersonModelRepository
from ..retrieval import invalidate_answers
from ..security import current_actor
from ..capture_planner import plan

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["person-model"])


class NotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)


def _authorized(session: Session, subject_id: str, actor: Actor) -> None:
    grant = session.scalar(select(Consent).where(
        Consent.subject_id == subject_id,
        Consent.granted_by_actor_id == actor.actor_id,
        Consent.scope == "RECORDING", Consent.status == "granted",
    ))
    if grant is None:
        raise NotFound("Subject not found")


def _memory(session: Session, subject_id: str, memory_id: str) -> MemoryItem:
    item = session.scalar(select(MemoryItem).join(Episode).where(
        Episode.subject_id == subject_id, MemoryItem.memory_item_id == memory_id,
        MemoryItem.deleted_at.is_(None),
    ))
    if item is None:
        raise NotFound("Memory not found")
    return item


@router.get("/memories")
def memories(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    rows = session.execute(select(MemoryItem, Episode).join(Episode).where(
        Episode.subject_id == subject_id, MemoryItem.deleted_at.is_(None)
    ).order_by(Episode.created_at.desc(), MemoryItem.ordinal)).all()
    items = []
    for memory, episode in rows:
        sources = [session.get(Evidence, eid) for eid in memory.evidence_ids]
        items.append({
            "memory_item_id": memory.memory_item_id, "episode_id": episode.episode_id,
            "content": memory.content, "memory_type": memory.memory_type,
            "domain": (memory.item_metadata or {}).get("domain"),
            "source_type": memory.source_type, "confidence": memory.confidence,
            "model_version": memory.model_version, "prompt_version": memory.prompt_version,
            "schema_version": memory.schema_version,
            "recorded_at": as_utc(episode.recorded_at).isoformat(),
            "transcript": episode.transcript,
            "stt_model_version": episode.stt_model_version,
            "evidence": [{"evidence_id": source.evidence_id,
                          "excerpt": source.excerpt, "source_type": source.source_type,
                          "source_ref": source.source_ref, "span_start": source.span_start,
                          "span_end": source.span_end} for source in sources if source],
        })
    return {"subject_id": subject_id, "items": items}


@router.get("/episodes")
def episodes(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    rows = list(session.scalars(select(Episode).where(
        Episode.subject_id == subject_id
    ).order_by(Episode.created_at.desc())))
    return {"subject_id": subject_id, "items": [{
        "episode_id": item.episode_id, "status": item.status,
        "source": item.source, "recorded_at": as_utc(item.recorded_at).isoformat(),
        "duration_ms": item.duration_ms, "transcript": item.transcript,
        "stt_backend": item.stt_backend, "stt_model_version": item.stt_model_version,
        "model_version": item.model_version, "error_code": item.error_code,
    } for item in rows]}


@router.get("/person-model")
def person_model(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    revision = session.get(ModelRevision, subject_id)
    traits = list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id == subject_id)))
    facts = list(session.scalars(select(GraphFact).where(GraphFact.subject_id == subject_id)))
    return {
        "subject_id": subject_id, "version": revision.version if revision else 0,
        "domains": [{"domain": domain, "traits": [{
            "trait_id": item.trait_id, "domain": item.domain,
            "statement": item.statement, "confidence": item.confidence,
            "source_type": item.source_type, "evidence_ids": item.evidence_ids,
            "counter_evidence_ids": item.counter_evidence_ids,
            "memory_item_ids": item.memory_item_ids, "status": item.status,
            "model_version": item.model_version,
            **({"context": item.context} if item.context is not None else {}),
            **({"valid_from": as_utc(item.valid_from).isoformat()} if item.valid_from else {}),
            **({"valid_to": as_utc(item.valid_to).isoformat()} if item.valid_to else {}),
        } for item in traits if item.domain == domain]} for domain in PERSON_DOMAINS],
        "graph_facts": [{"fact_id": fact.fact_id, "subject_id": fact.subject_id,
                         "kind": fact.kind, "content": fact.content,
                         "evidence_ids": fact.evidence_ids, "model_version": fact.model_version,
                         **({"valid_from": as_utc(fact.valid_from).isoformat()} if fact.valid_from else {}),
                         **({"valid_to": as_utc(fact.valid_to).isoformat()} if fact.valid_to else {})} for fact in facts],
    }


@router.get("/questions")
def questions(subject_id: str, actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    rows = plan(session, subject_id)
    session.commit()
    return {"subject_id": subject_id, "items": [{
        "question_id": item.question_id, "subject_id": item.subject_id,
        "text": item.text,
        "target_domain": item.target_domain, "reason": item.reason,
        "evidence_ids": item.evidence_ids, "status": item.status,
    } for item in rows]}


@router.patch("/memories/{memory_id}")
def correct_memory(subject_id: str, memory_id: str, body: Correction, request: Request,
                   actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    memory = _memory(session, subject_id, memory_id)
    content = body.content.strip()
    if not content:
        raise NotFound("Correction is empty")
    audit_id = "audit_" + uuid4().hex[:16]
    evidence_id = "ev_" + uuid4().hex[:16]
    session.add(MemoryAudit(audit_id=audit_id, memory_item_id=memory_id,
                            actor_id=actor.actor_id, action="correct",
                            previous_content=memory.content, new_content=content,
                            created_at=utcnow()))
    session.add(Evidence(evidence_id=evidence_id, episode_id=memory.episode_id,
                         source_type="CALIBRATION", source_ref=f"audit:{audit_id}",
                         excerpt=content, confidence=1.0))
    memory.content = content
    memory.source_type = "CALIBRATION"
    memory.evidence_ids = [evidence_id]
    memory.confidence = 1.0
    # Auxiliary interpretations refer to the old statement. A human correction
    # cannot inherit its mood, environment, or previous merge instruction.
    memory.item_metadata = {"domain": (memory.item_metadata or {}).get("domain")}
    embedding = session.get(MemoryEmbedding, memory_id)
    if embedding is not None:
        session.delete(embedding)
    version = PersonModelRepository(session).rebuild(subject_id)
    invalidate_answers(session, request.app.state.object_store, subject_id)
    session.commit()
    return {"memory_item_id": memory_id, "model_version": version}


@router.delete("/memories/{memory_id}")
def delete_memory(subject_id: str, memory_id: str, request: Request,
                  actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    _authorized(session, subject_id, actor)
    memory = _memory(session, subject_id, memory_id)
    session.add(MemoryAudit(audit_id="audit_" + uuid4().hex[:16],
                            memory_item_id=memory_id, actor_id=actor.actor_id,
                            action="delete", previous_content=memory.content,
                            created_at=utcnow()))
    memory.deleted_at = utcnow()
    embedding = session.get(MemoryEmbedding, memory_id)
    if embedding is not None:
        session.delete(embedding)
    version = PersonModelRepository(session).rebuild(subject_id)
    invalidate_answers(session, request.app.state.object_store, subject_id)
    session.commit()
    return {"memory_item_id": memory_id, "model_version": version}
