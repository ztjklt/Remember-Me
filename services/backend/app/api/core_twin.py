"""Evidence-backed read path for the isolated iOS branch.

These Backend-owned response shapes are provisional Phase 2 shapes, not a change
to packages/contracts. The query routes to direct Subject evidence when it can
find a relevant excerpt. Otherwise it returns explicit uncertainty; it never
invents a statement and calls it the original person.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domains import DOMAINS, MEMORY_DOMAIN
from ..errors import MemoryNotFound, RequestInvalid, SubjectNotFound
from ..models import Actor, Consent, ConsentScope, Episode, Evidence, MemoryFeedback, MemoryItem, PersonModelSnapshot, as_utc, utcnow
from ..person_model import rebuild_person_model
from ..repositories.consents import ConsentRepository
from ..security import current_actor

router = APIRouter(prefix="/api/v1/subjects", tags=["core-twin"])

class EvidenceView(BaseModel):
    evidence_id: str
    source_type: str
    source_ref: str
    excerpt: str | None
    confidence: float | None


class MemoryView(BaseModel):
    memory_item_id: str
    episode_id: str
    recorded_at: datetime
    memory_type: str
    domain: str
    content: str
    source_type: str
    confidence: float
    evidence: list[EvidenceView]
    model_version: str
    prompt_version: str
    schema_version: str
    correction: str | None = None


class SubjectMemories(BaseModel):
    subject_id: str
    items: list[MemoryView]
    domain_counts: dict[str, int]


class PersonFact(BaseModel):
    memory_item_id: str
    episode_id: str
    content: str
    source_type: str
    evidence_ids: list[str]
    confidence: float
    recorded_at: datetime
    effective_at: datetime | None
    model_version: str


class PersonModelView(BaseModel):
    subject_id: str
    revision: int
    model_version: str
    source_memory_ids: list[str]
    domains: dict[str, list[PersonFact]]
    updated_at: datetime | None


class TwinQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=1000)
    cloud_twin_consent_id: str = Field(min_length=1)


class TwinAnswer(BaseModel):
    subject_id: str
    question: str
    answer: str
    response_type: str
    confidence: float
    evidence: list[EvidenceView]
    model_version: str | None


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_content: str = Field(min_length=1, max_length=5000)


class CorrectionView(BaseModel):
    memory_item_id: str
    proposed_content: str
    status: str


def _can_read_subject(session: Session, *, subject_id: str, actor_id: str) -> bool:
    # An Actor may read their own captured Episodes after consent revocation,
    # just as the Phase 1 Episode result remains readable. A grant also lets a
    # newly seeded Actor see an empty Memory list before their first capture.
    own_episode = session.scalar(
        select(Episode.episode_id).where(
            Episode.subject_id == subject_id, Episode.actor_id == actor_id
        ).limit(1)
    )
    own_consent = session.scalar(
        select(Consent.consent_id).where(
            Consent.subject_id == subject_id,
            Consent.granted_by_actor_id == actor_id,
        ).limit(1)
    )
    return own_episode is not None or own_consent is not None


def _memories(session: Session, *, subject_id: str, actor_id: str) -> list[MemoryView]:
    pairs = session.execute(
        select(MemoryItem, Episode)
        .join(Episode, MemoryItem.episode_id == Episode.episode_id)
        .where(
            Episode.subject_id == subject_id,
            Episode.actor_id == actor_id,
            Episode.status == "ready",
        )
        .order_by(Episode.recorded_at.desc(), MemoryItem.ordinal)
    ).all()
    items: list[MemoryView] = []
    for memory, episode in pairs:
        feedback = session.get(MemoryFeedback, memory.memory_item_id)
        sources = session.scalars(
            select(Evidence).where(
                Evidence.episode_id == episode.episode_id,
                Evidence.evidence_id.in_(memory.evidence_ids),
            )
        ).all()
        evidence = [
            EvidenceView(
                evidence_id=source.evidence_id,
                source_type=source.source_type,
                source_ref=source.source_ref,
                excerpt=source.excerpt,
                confidence=source.confidence,
            )
            for source in sources
        ]
        items.append(
            MemoryView(
                memory_item_id=memory.memory_item_id,
                episode_id=episode.episode_id,
                recorded_at=as_utc(episode.recorded_at),
                memory_type=memory.memory_type,
                domain=MEMORY_DOMAIN.get(memory.memory_type, "Unclassified"),
                content=memory.content,
                source_type=memory.source_type,
                confidence=memory.confidence,
                evidence=evidence,
                model_version=memory.model_version,
                prompt_version=memory.prompt_version,
                schema_version=memory.schema_version,
                correction=feedback.proposed_content if feedback else None,
            )
        )
    return items


@router.get("/{subject_id}/memories", response_model=SubjectMemories)
def list_memories(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> SubjectMemories:
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    items = _memories(session, subject_id=subject_id, actor_id=actor.actor_id)
    counts = {domain: 0 for domain in DOMAINS}
    counts["Unclassified"] = 0
    for item in items:
        counts[item.domain] += 1
    return SubjectMemories(subject_id=subject_id, items=items, domain_counts=counts)


@router.get("/{subject_id}/person-model", response_model=PersonModelView)
def get_person_model(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> PersonModelView:
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    if snapshot is None:
        return PersonModelView(
            subject_id=subject_id, revision=0, model_version="person-preview-r0",
            source_memory_ids=[],
            domains={domain: [] for domain in (*DOMAINS, "Unclassified")},
            updated_at=None,
        )
    return PersonModelView(
        subject_id=subject_id, revision=snapshot.revision,
        model_version=f"person-preview-r{snapshot.revision}",
        source_memory_ids=snapshot.source_memory_ids,
        domains=snapshot.domains,
        updated_at=as_utc(snapshot.updated_at),
    )


def _owned_memory(
    session: Session, *, subject_id: str, memory_item_id: str, actor_id: str
) -> MemoryItem:
    memory = session.scalar(
        select(MemoryItem).join(Episode, MemoryItem.episode_id == Episode.episode_id)
        .where(
            MemoryItem.memory_item_id == memory_item_id,
            Episode.subject_id == subject_id,
            Episode.actor_id == actor_id,
            Episode.status == "ready",
        )
    )
    if memory is None:
        raise MemoryNotFound("No accessible Memory")
    return memory


@router.put("/{subject_id}/memories/{memory_item_id}/correction", response_model=CorrectionView)
def correct_memory(
    subject_id: str,
    memory_item_id: str,
    payload: CorrectionRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> CorrectionView:
    _owned_memory(
        session, subject_id=subject_id, memory_item_id=memory_item_id,
        actor_id=actor.actor_id,
    )
    proposed = payload.proposed_content.strip()
    if not proposed:
        raise RequestInvalid("proposed_content must contain text")
    feedback = session.get(MemoryFeedback, memory_item_id)
    if feedback is None:
        feedback = MemoryFeedback(
            memory_item_id=memory_item_id,
            actor_id=actor.actor_id,
            status="CORRECT",
            proposed_content=proposed,
            updated_at=utcnow(),
        )
        session.add(feedback)
    else:
        feedback.proposed_content = proposed
        feedback.updated_at = utcnow()
    session.flush()
    rebuild_person_model(session, subject_id=subject_id, actor_id=actor.actor_id)
    session.commit()
    return CorrectionView(
        memory_item_id=memory_item_id, proposed_content=proposed, status="CORRECT"
    )


@router.delete("/{subject_id}/memories/{memory_item_id}/correction", status_code=status.HTTP_204_NO_CONTENT)
def remove_correction(
    subject_id: str,
    memory_item_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> Response:
    _owned_memory(
        session, subject_id=subject_id, memory_item_id=memory_item_id,
        actor_id=actor.actor_id,
    )
    session.execute(delete(MemoryFeedback).where(MemoryFeedback.memory_item_id == memory_item_id))
    rebuild_person_model(session, subject_id=subject_id, actor_id=actor.actor_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{subject_id}/memories/{memory_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    subject_id: str,
    memory_item_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> Response:
    memory = _owned_memory(
        session, subject_id=subject_id, memory_item_id=memory_item_id,
        actor_id=actor.actor_id,
    )
    session.execute(delete(MemoryFeedback).where(MemoryFeedback.memory_item_id == memory_item_id))
    episode_id = memory.episode_id
    session.delete(memory)
    session.flush()
    remaining = session.scalars(
        select(MemoryItem).where(MemoryItem.episode_id == episode_id)
        .order_by(MemoryItem.ordinal)
    ).all()
    for ordinal, item in enumerate(remaining):
        item.ordinal = ordinal
    rebuild_person_model(session, subject_id=subject_id, actor_id=actor.actor_id)
    session.commit()
    # The original Episode and source Evidence remain as the provenance record.
    # All derived Memory/Twin surfaces read current MemoryItem rows, so deletion
    # stops this claim from being returned immediately.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _tokens(value: str) -> set[str]:
    """Small, deterministic relevance check; not a semantic Twin model."""
    text = value.lower()
    han_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    han = {
        run[index : index + 2]
        for run in han_runs
        for index in range(max(0, len(run) - 1))
    }
    latin = {word for word in re.findall(r"[a-z0-9]+", text) if len(word) > 2}
    return han | latin


GENERIC_QUERY_TOKENS = {
    "我喜", "最喜", "喜欢", "我想", "想要", "什么", "怎么", "为何",
    "是否", "的是", "是谁", "is", "are", "the", "what", "like",
}


@router.post("/{subject_id}/twin/query", response_model=TwinAnswer)
def query_twin(
    subject_id: str,
    payload: TwinQuestion,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> TwinAnswer:
    ConsentRepository(session).require_active(
        payload.cloud_twin_consent_id,
        subject_id=subject_id,
        scope=ConsentScope.CLOUD_TWIN,
        actor_id=actor.actor_id,
    )
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    words = _tokens(payload.question)
    matches: list[tuple[int, MemoryView, EvidenceView]] = []
    inferred_matches: list[tuple[int, MemoryView, EvidenceView]] = []
    for item in _memories(session, subject_id=subject_id, actor_id=actor.actor_id):
        if item.correction is not None:
            continue
        # A shared verb such as 喜欢 does not mean that a statement about coffee
        # answers a question about cities. Route to ORIGINAL only when a more
        # specific phrase is shared; otherwise admit uncertainty.
        for evidence in item.evidence:
            if not evidence.excerpt:
                continue
            overlap = len(
                (words & (_tokens(item.content) | _tokens(evidence.excerpt)))
                - GENERIC_QUERY_TOKENS
            )
            if overlap == 0:
                continue
            if item.source_type == "SUBJECT" and evidence.source_type == "SUBJECT":
                matches.append((overlap, item, evidence))
            elif evidence.source_type == "AI_INFERENCE":
                inferred_matches.append((overlap, item, evidence))
    if matches:
        overlap, item, evidence = max(
            matches, key=lambda candidate: (
                candidate[0], candidate[1].confidence,
                candidate[1].recorded_at,
            )
        )
        return TwinAnswer(
            subject_id=subject_id,
            question=payload.question,
            answer=evidence.excerpt or item.content,
            response_type="ORIGINAL",
            confidence=round(min(item.confidence, evidence.confidence if evidence.confidence is not None else 1.0), 3),
            evidence=[evidence],
            model_version=item.model_version,
        )
    if inferred_matches:
        _, item, evidence = max(
            inferred_matches, key=lambda candidate: (
                candidate[0], candidate[1].confidence,
                candidate[1].recorded_at,
            )
        )
        return TwinAnswer(
            subject_id=subject_id,
            question=payload.question,
            answer=f"录音中有相关片段，但尚未确认说话人：{evidence.excerpt}",
            response_type="SIMULATION",
            confidence=round(min(item.confidence, evidence.confidence if evidence.confidence is not None else 1.0, 0.5), 3),
            evidence=[evidence],
            model_version=item.model_version,
        )
    return TwinAnswer(
        subject_id=subject_id,
        question=payload.question,
        answer="目前没有足够的本人原始证据，无法可靠回答。",
        response_type="SIMULATION",
        confidence=0,
        evidence=[],
        model_version=None,
    )
