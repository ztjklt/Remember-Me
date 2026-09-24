"""Evidence-backed read path for the isolated iOS branch.

These Backend-owned response shapes are provisional Phase 2 shapes, not a change
to packages/contracts. The query routes to direct Subject evidence when it can
find a relevant excerpt. Otherwise it returns explicit uncertainty; it never
invents a statement and calls it the original person.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import SubjectNotFound
from ..models import Actor, Consent, ConsentScope, Episode, Evidence, MemoryItem, as_utc
from ..repositories.consents import ConsentRepository
from ..security import current_actor

router = APIRouter(prefix="/api/v1/subjects", tags=["core-twin"])

DOMAINS = (
    "Identity", "Episodic Memory", "Relationships", "Preferences",
    "Values & Beliefs", "Decision Patterns", "Expression",
)
MEMORY_DOMAIN = {
    "EVENT": "Episodic Memory",
    "RELATIONSHIP": "Relationships",
    "PREFERENCE": "Preferences",
    "VALUE": "Values & Beliefs",
}


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


class SubjectMemories(BaseModel):
    subject_id: str
    items: list[MemoryView]
    domain_counts: dict[str, int]


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
    for item in _memories(session, subject_id=subject_id, actor_id=actor.actor_id):
        if item.source_type != "SUBJECT":
            continue
        # A shared verb such as 喜欢 does not mean that a statement about coffee
        # answers a question about cities. Route to ORIGINAL only when a more
        # specific phrase is shared; otherwise admit uncertainty.
        overlap = len((words & _tokens(item.content)) - GENERIC_QUERY_TOKENS)
        if overlap == 0:
            continue
        for evidence in item.evidence:
            if evidence.source_type == "SUBJECT" and evidence.excerpt:
                matches.append((overlap, item, evidence))
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
            confidence=round(min(item.confidence, evidence.confidence or 1.0), 3),
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
