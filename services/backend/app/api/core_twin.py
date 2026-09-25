"""Evidence-backed read path for the isolated iOS branch.

These Backend-owned response shapes are provisional Phase 2 shapes, not a change
to packages/contracts. The query routes to direct Subject evidence when it can
find a relevant excerpt. Otherwise it returns explicit uncertainty; it never
invents a statement and calls it the original person.
"""

import re
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domains import DOMAINS, MEMORY_DOMAIN
from ..errors import (
    AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable,
    MemoryNotFound, RequestInvalid, SubjectNotFound,
)
from ..models import Actor, Consent, ConsentScope, Episode, Evidence, MemoryFeedback, MemoryItem, PersonModelSnapshot, as_utc, utcnow
from ..person_model import rebuild_person_model, refresh_after_mutation
from ..repositories.consents import ConsentRepository
from ..security import current_actor, require_subject_owner

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
    trait_id: str | None = None
    memory_item_id: str
    episode_id: str
    content: str
    source_type: str
    evidence_ids: list[str]
    confidence: float
    recorded_at: datetime
    effective_at: datetime | None
    model_version: str
    context: str | None = None
    counter_evidence_ids: list[str] = []
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    status: str = "current"
    conflict_type: str | None = None
    support_memory_ids: list[str] = []
    counter_memory_ids: list[str] = []


class PersonModelView(BaseModel):
    subject_id: str
    revision: int
    model_version: str
    source_memory_ids: list[str]
    domains: dict[str, list[PersonFact]]
    calibration_updates: list[dict] = []
    updated_at: datetime | None
    processing_state: str = "ready"


class GraphNode(BaseModel):
    node_id: str
    kind: str
    label: str
    recorded_at: datetime | None = None
    domain: str | None = None
    source_type: str | None = None
    support_memory_ids: list[str] = []


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: str
    support_memory_ids: list[str] = []


class MemoryGraphView(BaseModel):
    subject_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


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


class TwinSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    evidence_ids: list[str] = Field(max_length=3)
    answer: str | None = Field(default=None, max_length=1000)
    model_version: str = Field(min_length=1)


class TwinAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str
    answer: str | None
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    model_version: str = Field(min_length=1)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposed_content: str = Field(min_length=1, max_length=5000)


class CorrectionView(BaseModel):
    memory_item_id: str
    proposed_content: str
    status: str


def _can_read_subject(session: Session, *, subject_id: str, actor_id: str) -> bool:
    try:
        require_subject_owner(session, subject_id=subject_id, actor_id=actor_id)
    except SubjectNotFound:
        return False
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
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> PersonModelView:
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    if (request.app.state.settings.ai_backend == "http"
            and (snapshot is None or snapshot.synthesis_model_version is None)):
        try:
            snapshot = rebuild_person_model(
                session, subject_id=subject_id, actor_id=actor.actor_id,
                settings=request.app.state.settings,
            )
            session.commit()
        except (AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable):
            # The source mutation already committed. Keep the invalidated
            # snapshot visible and retry synthesis on a later read.
            session.rollback()
            snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    if snapshot is None:
        return PersonModelView(
            subject_id=subject_id, revision=0,
            model_version="person-empty-r0" if request.app.state.settings.ai_backend == "http" else "person-preview-r0",
            source_memory_ids=[],
            domains={domain: [] for domain in (*DOMAINS, "Unclassified")},
            calibration_updates=[],
            updated_at=None,
            processing_state="empty",
        )
    stale = request.app.state.settings.ai_backend == "http" and snapshot.synthesis_model_version is None
    return PersonModelView(
        subject_id=subject_id, revision=snapshot.revision,
        model_version=snapshot.synthesis_model_version or (
            f"person-rebuilding-r{snapshot.revision}" if stale else f"person-preview-r{snapshot.revision}"
        ),
        source_memory_ids=snapshot.source_memory_ids,
        domains=snapshot.domains,
        calibration_updates=snapshot.calibration_updates,
        updated_at=as_utc(snapshot.updated_at),
        processing_state="rebuilding" if stale else "ready",
    )


@router.get("/{subject_id}/memory-graph", response_model=MemoryGraphView)
def get_memory_graph(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> MemoryGraphView:
    """Build a bounded provenance/timeline graph from current, undisputed claims."""
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    items = [
        item for item in _memories(session, subject_id=subject_id, actor_id=actor.actor_id)
        if item.correction is None
    ][:200]
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen_episodes: set[str] = set()
    seen_evidence: set[str] = set()
    by_domain: dict[str, list[MemoryView]] = {}
    for item in items:
        memory_id = f"memory:{item.memory_item_id}"
        episode_id = f"episode:{item.episode_id}"
        nodes.append(GraphNode(
            node_id=memory_id, kind="MEMORY", label=item.content,
            recorded_at=item.recorded_at, domain=item.domain,
            source_type=item.source_type,
        ))
        if episode_id not in seen_episodes:
            nodes.append(GraphNode(
                node_id=episode_id, kind="EPISODE", label=item.episode_id,
                recorded_at=item.recorded_at,
            ))
            seen_episodes.add(episode_id)
        edges.append(GraphEdge(
            source_id=memory_id, target_id=episode_id, relation="CAPTURED_IN"
        ))
        for source in item.evidence:
            evidence_id = f"evidence:{source.evidence_id}"
            if evidence_id not in seen_evidence:
                nodes.append(GraphNode(
                    node_id=evidence_id, kind="EVIDENCE",
                    label=source.excerpt or source.source_ref,
                    source_type=source.source_type,
                ))
                seen_evidence.add(evidence_id)
            edges.append(GraphEdge(
                source_id=memory_id, target_id=evidence_id, relation="SUPPORTED_BY"
            ))
        by_domain.setdefault(item.domain, []).append(item)
    for domain_items in by_domain.values():
        ordered = sorted(domain_items, key=lambda item: (item.recorded_at, item.memory_item_id))
        for earlier, later in zip(ordered, ordered[1:]):
            if earlier.recorded_at < later.recorded_at:
                edges.append(GraphEdge(
                    source_id=f"memory:{earlier.memory_item_id}",
                    target_id=f"memory:{later.memory_item_id}",
                    relation="PRECEDES_IN_DOMAIN",
                ))
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    if snapshot is not None:
        node_ids = {node.node_id for node in nodes}
        for facts in snapshot.domains.values():
            for fact in facts:
                for counter_id in fact.get("counter_evidence_ids", []):
                    edge = GraphEdge(
                        source_id=f"memory:{fact['memory_item_id']}",
                        target_id=f"evidence:{counter_id}", relation="CONTRADICTED_BY",
                    )
                    if edge.source_id in node_ids and edge.target_id in node_ids:
                        edges.append(edge)
        graph = snapshot.semantic_graph or {}
        active_memory_ids = {item.memory_item_id for item in items}
        for raw in graph.get("nodes", []):
            if set(raw.get("support_memory_ids", [])) <= active_memory_ids:
                nodes.append(GraphNode.model_validate(raw))
        node_ids = {node.node_id for node in nodes}
        for raw in graph.get("edges", []):
            if (raw.get("source_id") in node_ids and raw.get("target_id") in node_ids
                    and set(raw.get("support_memory_ids", [])) <= active_memory_ids):
                edges.append(GraphEdge.model_validate(raw))
    return MemoryGraphView(subject_id=subject_id, nodes=nodes, edges=edges)


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
    request: Request,
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
    refresh_after_mutation(session, subject_id=subject_id, actor_id=actor.actor_id,
                           settings=request.app.state.settings)
    session.commit()
    return CorrectionView(
        memory_item_id=memory_item_id, proposed_content=proposed, status="CORRECT"
    )


@router.delete("/{subject_id}/memories/{memory_item_id}/correction", status_code=status.HTTP_204_NO_CONTENT)
def remove_correction(
    subject_id: str,
    memory_item_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> Response:
    _owned_memory(
        session, subject_id=subject_id, memory_item_id=memory_item_id,
        actor_id=actor.actor_id,
    )
    session.execute(delete(MemoryFeedback).where(MemoryFeedback.memory_item_id == memory_item_id))
    refresh_after_mutation(session, subject_id=subject_id, actor_id=actor.actor_id,
                           settings=request.app.state.settings)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{subject_id}/memories/{memory_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    subject_id: str,
    memory_item_id: str,
    request: Request,
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
    refresh_after_mutation(session, subject_id=subject_id, actor_id=actor.actor_id,
                           settings=request.app.state.settings)
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


def _real_twin(
    session: Session, *, subject_id: str, actor_id: str,
    question: str, settings,
) -> TwinAnswer:
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor_id))
    if snapshot is None or snapshot.synthesis_model_version is None:
        snapshot = rebuild_person_model(
            session, subject_id=subject_id, actor_id=actor_id, settings=settings,
        )
        session.commit()
    blocked = {
        memory_id for facts in snapshot.domains.values() for fact in facts
        if fact.get("status") in {"superseded", "disputed"}
        for memory_id in fact.get("support_memory_ids", [fact["memory_item_id"]])
    }
    items = [item for item in _memories(session, subject_id=subject_id, actor_id=actor_id)
             if item.correction is None and item.memory_item_id not in blocked]
    candidates = []
    evidence_by_id: dict[str, EvidenceView] = {}
    for item in items:
        for evidence in item.evidence:
            if not evidence.excerpt or evidence.evidence_id in evidence_by_id:
                continue
            evidence_by_id[evidence.evidence_id] = evidence
            candidates.append({
                "evidence_id": evidence.evidence_id,
                "memory_item_id": item.memory_item_id,
                "excerpt": evidence.excerpt[:1000],
                "memory_content": item.content[:1000],
                "source_type": evidence.source_type,
                "recorded_at": item.recorded_at.isoformat(),
                "confidence": min(item.confidence, evidence.confidence or 1.0),
            })
    for feedback in snapshot.calibration_updates:
        if not feedback.get("human_answer"):
            continue
        evidence_id = f"calibration:{feedback['calibration_id']}"
        view = EvidenceView(
            evidence_id=evidence_id, source_type="CALIBRATION",
            source_ref=evidence_id, excerpt=feedback["human_answer"], confidence=0.7,
        )
        evidence_by_id[evidence_id] = view
        candidates.append({
            "evidence_id": evidence_id, "memory_item_id": evidence_id,
            "excerpt": feedback["human_answer"][:1000],
            "memory_content": feedback["question"][:1000],
            "source_type": "CALIBRATION", "recorded_at": feedback["confirmed_at"],
            "confidence": 0.7,
        })
    if len(candidates) > 100:
        raise AiUnavailable("Twin evidence corpus exceeds the semantic retrieval window")
    traits = [{
        "trait_id": fact.get("trait_id") or fact["memory_item_id"],
        "domain": domain, "statement": fact["content"],
        "evidence_ids": fact["evidence_ids"], "context": fact.get("context"),
        "confidence": fact["confidence"],
    } for domain, facts in snapshot.domains.items() for fact in facts
        if fact.get("status", "current") == "current"]
    if len(traits) > 100:
        raise AiUnavailable("Twin trait corpus exceeds the semantic retrieval window")
    if not candidates:
        return TwinAnswer(
            subject_id=subject_id, question=question,
            answer="目前没有足够证据，无法可靠回答。", response_type="SIMULATION",
            confidence=0, evidence=[], model_version=snapshot.synthesis_model_version,
        )
    try:
        response = httpx.post(
            settings.ai_core_url.rstrip("/") + "/twin/answer",
            json={"question": question, "evidence": candidates, "traits": traits},
            timeout=httpx.Timeout(settings.ai_timeout_seconds), follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise AiTimeout("Twin Agent timed out") from exc
    except httpx.TransportError as exc:
        raise AiUnavailable("Twin Agent unavailable") from exc
    if response.status_code in {408, 504}:
        raise AiTimeout("Twin Agent timed out")
    if response.status_code in {429, 503}:
        raise AiUnavailable("Twin Agent unavailable")
    if not response.is_success:
        raise AiFailed("Twin Agent failed")
    try:
        generated = TwinAgentResult.model_validate(response.json())
    except (ValueError, TypeError) as exc:
        raise AiSchemaInvalid("Twin Agent violated its response schema") from exc
    if generated.model_version.startswith(("fixture-", "fake-")):
        raise AiSchemaInvalid("Twin Agent returned a fixture model")
    if len(generated.evidence_ids) != len(set(generated.evidence_ids)) or not set(generated.evidence_ids) <= evidence_by_id.keys():
        raise AiSchemaInvalid("Twin Agent cited inaccessible evidence")
    cited = [evidence_by_id[eid] for eid in generated.evidence_ids]
    if generated.route == "ORIGINAL":
        if len(cited) != 1 or cited[0].source_type != "SUBJECT":
            raise AiSchemaInvalid("ORIGINAL requires one direct Subject excerpt")
        return TwinAnswer(
            subject_id=subject_id, question=question, answer=cited[0].excerpt or "",
            response_type="ORIGINAL", confidence=min(generated.confidence, cited[0].confidence or 1.0),
            evidence=cited, model_version=generated.model_version,
        )
    if generated.route == "SIMULATION":
        if not cited or not generated.answer or not generated.answer.strip():
            raise AiSchemaInvalid("SIMULATION requires text and citations")
        return TwinAnswer(
            subject_id=subject_id, question=question, answer=generated.answer.strip(),
            response_type="SIMULATION", confidence=min(generated.confidence, 0.8),
            evidence=cited, model_version=generated.model_version,
        )
    if generated.route != "REFUSE" or cited:
        raise AiSchemaInvalid("Twin Agent returned an invalid refusal")
    return TwinAnswer(
        subject_id=subject_id, question=question,
        answer="目前没有足够证据，无法可靠回答。", response_type="SIMULATION",
        confidence=0, evidence=[], model_version=generated.model_version,
    )


@router.post("/{subject_id}/twin/query", response_model=TwinAnswer)
def query_twin(
    subject_id: str,
    payload: TwinQuestion,
    request: Request,
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
    settings = request.app.state.settings
    if settings.ai_backend == "http":
        return _real_twin(
            session, subject_id=subject_id, actor_id=actor.actor_id,
            question=payload.question, settings=settings,
        )
    words = _tokens(payload.question)
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    statuses = {
        fact["memory_item_id"]: fact.get("status", "current")
        for facts in snapshot.domains.values() for fact in facts
    } if snapshot is not None else {}
    matches: list[tuple[int, MemoryView, EvidenceView]] = []
    inferred_matches: list[tuple[int, MemoryView, EvidenceView]] = []
    candidates: list[dict[str, str]] = []
    candidate_evidence: dict[str, EvidenceView] = {}
    for item in _memories(session, subject_id=subject_id, actor_id=actor.actor_id):
        if item.correction is not None or statuses.get(item.memory_item_id, "current") != "current":
            continue
        # A shared verb such as 喜欢 does not mean that a statement about coffee
        # answers a question about cities. Route to ORIGINAL only when a more
        # specific phrase is shared; otherwise admit uncertainty.
        for evidence in item.evidence:
            if not evidence.excerpt:
                continue
            if (
                evidence.source_type in {"SUBJECT", "AI_INFERENCE"}
                and evidence.evidence_id not in candidate_evidence
                and len(candidates) < 20
            ):
                candidates.append({
                    "evidence_id": evidence.evidence_id,
                    "excerpt": evidence.excerpt[:1000],
                    "memory_content": item.content[:1000],
                    "source_type": evidence.source_type,
                })
                candidate_evidence[evidence.evidence_id] = evidence
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
    settings = request.app.state.settings
    if settings.ai_backend == "http" and candidates:
        try:
            response = httpx.post(
                settings.ai_core_url.rstrip("/") + "/twin/simulate",
                json={"question": payload.question, "candidates": candidates},
                timeout=httpx.Timeout(settings.ai_timeout_seconds),
                follow_redirects=False,
            )
        except httpx.TimeoutException as exc:
            raise AiTimeout("Twin simulation timed out") from exc
        except httpx.TransportError as exc:
            raise AiUnavailable("Twin simulation unavailable") from exc
        if response.status_code in {408, 504}:
            raise AiTimeout("Twin simulation timed out")
        if response.status_code in {429, 503}:
            raise AiUnavailable("Twin simulation unavailable")
        if not response.is_success:
            raise AiFailed("Twin simulation failed")
        try:
            generated = TwinSimulation.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            raise AiSchemaInvalid("Twin simulation violated its schema") from exc
        if generated.model_version.startswith("fixture-"):
            raise AiSchemaInvalid("Twin simulation used a fixture model")
        cited = [candidate_evidence[evidence_id] for evidence_id in generated.evidence_ids
                 if evidence_id in candidate_evidence]
        if len(cited) != len(generated.evidence_ids) or len(set(generated.evidence_ids)) != len(cited):
            raise AiSchemaInvalid("Twin simulation cited inaccessible evidence")
        if generated.supported:
            if not cited:
                raise AiSchemaInvalid("Twin retrieval omitted evidence")
            excerpts = " / ".join((evidence.excerpt or "")[:180] for evidence in cited)
            answer = generated.answer.strip() if generated.answer else excerpts
            return TwinAnswer(
                subject_id=subject_id, question=payload.question,
                answer=f"根据相关录音推测，仍需本人核实：{answer}",
                response_type="SIMULATION", confidence=0.25,
                evidence=cited, model_version=generated.model_version,
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
