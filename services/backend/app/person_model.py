"""Evidence-grounded temporal Person Model materialization.

Real AI deployments use the structured Persona worker. Fake deployments keep a
clearly versioned local fixture for tests; they never masquerade as a real model.
"""

import hashlib
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domains import DOMAINS, MEMORY_DOMAIN
from .config import Settings
from .errors import AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable
from .models import (
    CalibrationSession, Consent, Episode, Evidence, MemoryFeedback, MemoryItem,
    PersonModelSnapshot, as_utc, utcnow,
)


class _Trait(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: str
    statement: str = Field(min_length=2)
    support_memory_ids: list[str] = Field(min_length=1)
    counter_memory_ids: list[str]
    context: str | None
    confidence: float = Field(ge=0, le=1)
    status: str
    conflict_type: str | None


class _Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    kind: str
    support_memory_ids: list[str] = Field(min_length=1)


class _Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_name: str
    target_name: str
    relation: str
    support_memory_ids: list[str] = Field(min_length=1)


class _Persona(BaseModel):
    model_config = ConfigDict(extra="forbid")
    traits: list[_Trait]
    entities: list[_Entity]
    relations: list[_Relation]
    model_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)


def _stable_id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("\x1f".join(values).encode()).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _semantic_model(
    session: Session, pairs: list, settings: Settings,
) -> tuple[dict[str, list[dict]], dict, str]:
    if len(pairs) > 100:
        raise AiSchemaInvalid("Person Model exceeds the current 100-source synthesis window")
    memories = {memory.memory_item_id: (memory, episode) for memory, episode in pairs}
    evidence_ids = {evidence_id for memory, _ in pairs for evidence_id in memory.evidence_ids}
    evidence = {
        row.evidence_id: row for row in session.scalars(
            select(Evidence).where(Evidence.evidence_id.in_(evidence_ids))
        )
    } if evidence_ids else {}
    payload = {"memories": [{
        "memory_item_id": memory.memory_item_id,
        "content": memory.content[:2000],
        "domain_hint": MEMORY_DOMAIN.get(memory.memory_type, "Unclassified"),
        "source_type": memory.source_type,
        "evidence_ids": memory.evidence_ids[:10],
        "excerpts": [evidence[item].excerpt[:1000] for item in memory.evidence_ids[:10]
                     if item in evidence and evidence[item].excerpt],
        "recorded_at": as_utc(episode.recorded_at).isoformat(),
        "effective_at": as_utc(memory.effective_at).isoformat() if memory.effective_at else None,
        "confidence": memory.confidence,
    } for memory, episode in pairs]}
    if not pairs:
        return ({domain: [] for domain in (*DOMAINS, "Unclassified")},
                {"nodes": [], "edges": []}, "empty-persona-v1")
    if any(not item["excerpts"] for item in payload["memories"]):
        raise AiSchemaInvalid("Person Model source lacks a usable evidence excerpt")
    try:
        response = httpx.post(
            settings.ai_core_url.rstrip("/") + "/persona/reconcile",
            json=payload, timeout=httpx.Timeout(settings.ai_timeout_seconds),
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise AiTimeout("Persona synthesis timed out") from exc
    except httpx.TransportError as exc:
        raise AiUnavailable("Persona synthesis unavailable") from exc
    if response.status_code in {408, 504}:
        raise AiTimeout("Persona synthesis timed out")
    if response.status_code in {429, 503}:
        raise AiUnavailable("Persona synthesis unavailable")
    if not response.is_success:
        raise AiFailed("Persona synthesis failed")
    try:
        result = _Persona.model_validate(response.json())
    except (ValueError, TypeError) as exc:
        raise AiSchemaInvalid("Persona synthesis violated its schema") from exc
    if result.model_version.startswith(("fixture-", "fake-")) or result.schema_version != "persona-temporal-v1":
        raise AiSchemaInvalid("Persona synthesis did not use the real versioned worker")

    allowed = set(memories)
    def sources(ids: list[str]) -> list[tuple[MemoryItem, Episode]]:
        if not ids or len(ids) != len(set(ids)) or not set(ids) <= allowed:
            raise AiSchemaInvalid("Persona cited inaccessible or repeated Memory IDs")
        return [memories[item] for item in ids]

    domains: dict[str, list[dict]] = {domain: [] for domain in (*DOMAINS, "Unclassified")}
    for trait in result.traits:
        if trait.domain not in DOMAINS or trait.status not in {"current", "superseded", "disputed"}:
            raise AiSchemaInvalid("Persona returned an unknown domain or status")
        support = sources(trait.support_memory_ids)
        counters = sources(trait.counter_memory_ids) if trait.counter_memory_ids else []
        if set(trait.support_memory_ids) & set(trait.counter_memory_ids):
            raise AiSchemaInvalid("Persona mixed support and counter-evidence")
        if trait.status != "current" and not counters:
            raise AiSchemaInvalid("Non-current trait omitted counter-evidence")
        if trait.status == "superseded" and trait.conflict_type != "changed":
            raise AiSchemaInvalid("Superseded trait requires a genuine change")
        if trait.conflict_type not in {None, "changed", "context_dependent", "unresolved"}:
            raise AiSchemaInvalid("Persona returned an unknown conflict type")
        anchor, episode = support[0]
        starts = [as_utc(memory.effective_at or ep.recorded_at) for memory, ep in support]
        counter_times = [as_utc(memory.effective_at or ep.recorded_at) for memory, ep in counters]
        valid_from = min(starts)
        valid_to = min((time for time in counter_times if time > valid_from), default=None)
        support_evidence = list(dict.fromkeys(eid for memory, _ in support for eid in memory.evidence_ids))
        counter_evidence = list(dict.fromkeys(eid for memory, _ in counters for eid in memory.evidence_ids))
        source_types = {memory.source_type for memory, _ in support}
        domains[trait.domain].append({
            "trait_id": _stable_id("trait", trait.domain, trait.statement, *sorted(trait.support_memory_ids)),
            "memory_item_id": anchor.memory_item_id, "episode_id": episode.episode_id,
            "content": trait.statement, "source_type": next(iter(source_types)) if len(source_types) == 1 else "AI_INFERENCE",
            "evidence_ids": support_evidence, "confidence": min(trait.confidence, *(memory.confidence for memory, _ in support)),
            "recorded_at": as_utc(episode.recorded_at).isoformat(),
            "effective_at": as_utc(anchor.effective_at).isoformat() if anchor.effective_at else None,
            "model_version": result.model_version, "context": trait.context,
            "support_memory_ids": trait.support_memory_ids,
            "counter_memory_ids": trait.counter_memory_ids,
            "counter_evidence_ids": counter_evidence,
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat() if trait.status == "superseded" and valid_to else None,
            "status": trait.status, "conflict_type": trait.conflict_type,
        })
    graph_nodes = []
    graph_edges = []
    names = {}
    entity_sources: dict[str, set[str]] = {}
    for entity in result.entities:
        if entity.kind not in {"PERSON", "PLACE", "EVENT", "TOPIC"}:
            raise AiSchemaInvalid("Persona returned an unknown entity kind")
        support = sources(entity.support_memory_ids)
        key = entity.name.strip().casefold()
        if key in names:
            raise AiSchemaInvalid("Persona duplicated an entity")
        node_id = _stable_id("entity", entity.kind, key)
        names[key] = node_id
        entity_sources[key] = set(entity.support_memory_ids)
        graph_nodes.append({
            "node_id": node_id, "kind": entity.kind, "label": entity.name,
            "recorded_at": min(as_utc(ep.recorded_at) for _, ep in support).isoformat(),
            "source_type": "AI_INFERENCE", "support_memory_ids": entity.support_memory_ids,
        })
        for memory_id in entity.support_memory_ids:
            graph_edges.append({"source_id": node_id, "target_id": f"memory:{memory_id}",
                                "relation": "GROUNDED_IN"})
    for relation in result.relations:
        sources(relation.support_memory_ids)
        source_name = relation.source_name.strip().casefold()
        target_name = relation.target_name.strip().casefold()
        source_id = names.get(source_name)
        target_id = names.get(target_name)
        if not source_id or not target_id:
            raise AiSchemaInvalid("Persona relation referenced a missing entity")
        support = set(relation.support_memory_ids)
        if not support & (entity_sources[source_name] | entity_sources[target_name]):
            raise AiSchemaInvalid("Persona relation lacked source evidence for either entity")
        graph_edges.append({"source_id": source_id, "target_id": target_id,
                            "relation": relation.relation, "support_memory_ids": relation.support_memory_ids})
    return domains, {"nodes": graph_nodes, "edges": graph_edges}, result.model_version


def _preference_claim(value: str) -> tuple[str, bool] | None:
    """Only compare explicit first-person preference claims about the same text."""
    normalized = re.sub(r"[。！!,.，\s]", "", value)
    match = re.search(r"(?:我|本人)(?:现在|目前|以前|曾经)?(不喜欢|喜欢|讨厌|不爱|爱)(.+)", normalized)
    if not match:
        return None
    topic = match.group(2)
    if len(topic) < 2:
        return None
    return topic, match.group(1) in {"喜欢", "爱"}


def rebuild_person_model(
    session: Session, *, subject_id: str, actor_id: str,
    settings: Settings | None = None,
) -> PersonModelSnapshot:
    pairs = session.execute(
        select(MemoryItem, Episode)
        .join(Episode, MemoryItem.episode_id == Episode.episode_id)
        .where(
            Episode.subject_id == subject_id,
            Episode.actor_id == actor_id,
            Episode.status.in_(["ready", "modeling"]),
        )
        .order_by(Episode.recorded_at, MemoryItem.ordinal)
    ).all()
    feedback_ids = set(session.scalars(select(MemoryFeedback.memory_item_id)).all())
    domains: dict[str, list[dict]] = {
        domain: [] for domain in (*DOMAINS, "Unclassified")
    }
    source_ids: list[str] = []
    usable_pairs = []
    for memory, episode in pairs:
        if memory.memory_item_id in feedback_ids:
            continue
        usable_pairs.append((memory, episode))
        domain = MEMORY_DOMAIN.get(memory.memory_type, "Unclassified")
        domains[domain].append({
            "memory_item_id": memory.memory_item_id,
            "episode_id": episode.episode_id,
            "content": memory.content,
            "source_type": memory.source_type,
            "evidence_ids": memory.evidence_ids,
            "confidence": memory.confidence,
            "recorded_at": as_utc(episode.recorded_at).isoformat(),
            "effective_at": as_utc(memory.effective_at).isoformat() if memory.effective_at else None,
            "model_version": memory.model_version,
            "context": None,
            "counter_evidence_ids": [],
            "valid_from": as_utc(memory.effective_at or episode.recorded_at).isoformat(),
            "valid_to": None,
            "status": "current",
            "conflict_type": None,
        })
        source_ids.append(memory.memory_item_id)

    # The fixture path gives deterministic offline tests a conspicuously limited
    # baseline. A real deployment never substitutes this for semantic synthesis.
    preferences = domains["Preferences"]
    for earlier_index, earlier in enumerate(preferences):
        if earlier["source_type"] != "SUBJECT":
            continue
        first = _preference_claim(earlier["content"])
        if first is None:
            continue
        for later in preferences[earlier_index + 1:]:
            second = _preference_claim(later["content"])
            if later["source_type"] != "SUBJECT" or second is None:
                continue
            if first[0] != second[0] or first[1] == second[1]:
                continue
            earlier["counter_evidence_ids"] = list(later["evidence_ids"])
            later["counter_evidence_ids"] = list(earlier["evidence_ids"])
            if "现在" in later["content"] or "目前" in later["content"]:
                earlier["status"] = "superseded"
                earlier["valid_to"] = later["valid_from"]
                earlier["conflict_type"] = "changed"
                later["conflict_type"] = "changed"
            else:
                earlier["status"] = "disputed"
                later["status"] = "disputed"
                earlier["conflict_type"] = "unresolved"
                later["conflict_type"] = "unresolved"

    semantic_graph: dict = {"nodes": [], "edges": []}
    synthesis_model_version: str | None = None
    if settings is not None and settings.ai_backend == "http":
        domains, semantic_graph, synthesis_model_version = _semantic_model(
            session, usable_pairs, settings,
        )

    dimension_domains = {
        "decision": "Decision Patterns", "reasoning": "Decision Patterns",
        "value_priority": "Values & Beliefs", "emotional_reaction": "Relationships",
        "expression": "Expression",
    }
    calibrations = session.scalars(
        select(CalibrationSession)
        .join(Consent, CalibrationSession.cloud_twin_consent_id == Consent.consent_id)
        .where(
            CalibrationSession.subject_id == subject_id,
            CalibrationSession.actor_id == actor_id,
            CalibrationSession.confirmed_at.is_not(None),
            Consent.status == "granted",
        )
        .order_by(CalibrationSession.confirmed_at)
    ).all()
    calibration_updates = []
    for row in calibrations:
        gaps = row.dimension_gaps or {}
        assessment = row.ai_assessment or {}
        domains_with_gaps = {
            domain for dimension, domain in dimension_domains.items()
            if gaps.get(dimension) or assessment.get(dimension, {}).get("verdict") == "DIFFERENT"
        }
        calibration_updates.append({
            "calibration_id": row.calibration_id,
            "question": row.question,
            "human_answer": row.human_answer,
            "domains": sorted(domains_with_gaps),
            "source_type": "CALIBRATION",
            "status": "provisional",
            "confirmed_at": as_utc(row.confirmed_at).isoformat(),
            "model_version": assessment.get("model_version"),
            "locked_evidence_ids": list(row.evidence_ids),
        })

    snapshot = session.get(PersonModelSnapshot, (subject_id, actor_id))
    if snapshot is None:
        snapshot = PersonModelSnapshot(
            subject_id=subject_id, actor_id=actor_id, revision=1,
            source_memory_ids=source_ids, domains=domains,
            calibration_updates=calibration_updates, updated_at=utcnow(),
            semantic_graph=semantic_graph,
            synthesis_model_version=synthesis_model_version,
        )
        session.add(snapshot)
    elif (snapshot.source_memory_ids != source_ids or snapshot.domains != domains
          or snapshot.calibration_updates != calibration_updates
          or snapshot.semantic_graph != semantic_graph
          or snapshot.synthesis_model_version != synthesis_model_version):
        snapshot.revision += 1
        snapshot.source_memory_ids = source_ids
        snapshot.domains = domains
        snapshot.calibration_updates = calibration_updates
        snapshot.semantic_graph = semantic_graph
        snapshot.synthesis_model_version = synthesis_model_version
        snapshot.updated_at = utcnow()
    return snapshot


def invalidate_person_model(session: Session, *, subject_id: str, actor_id: str) -> None:
    """Commit a source change without waiting for an external model provider.

    Every stale derived trait, entity edge and calibration projection is removed
    in the same transaction as the correction, deletion or consent change.
    Subsequent real Twin queries may recompute, but can never read the old data.
    """
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor_id))
    if snapshot is None:
        snapshot = PersonModelSnapshot(
            subject_id=subject_id, actor_id=actor_id, revision=1,
            source_memory_ids=[],
            domains={domain: [] for domain in (*DOMAINS, "Unclassified")},
            calibration_updates=[], semantic_graph={"nodes": [], "edges": []},
            synthesis_model_version=None, updated_at=utcnow(),
        )
        session.add(snapshot)
        return
    snapshot.revision += 1
    snapshot.source_memory_ids = []
    snapshot.domains = {domain: [] for domain in (*DOMAINS, "Unclassified")}
    snapshot.semantic_graph = {"nodes": [], "edges": []}
    snapshot.calibration_updates = []
    snapshot.synthesis_model_version = None
    snapshot.updated_at = utcnow()


def refresh_after_mutation(
    session: Session, *, subject_id: str, actor_id: str, settings: Settings,
) -> None:
    if settings.ai_backend == "http":
        invalidate_person_model(session, subject_id=subject_id, actor_id=actor_id)
    else:
        rebuild_person_model(session, subject_id=subject_id, actor_id=actor_id)
