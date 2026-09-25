"""Deterministic, provenance-preserving Person Model preview materialization.

No unsupported trait is synthesized. The snapshot records which available
Memory claims support each domain and can be rebuilt after feedback/deletion.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domains import DOMAINS, MEMORY_DOMAIN
from .models import (
    CalibrationSession, Consent, Episode, MemoryFeedback, MemoryItem,
    PersonModelSnapshot, as_utc, utcnow,
)


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
    session: Session, *, subject_id: str, actor_id: str
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
    for memory, episode in pairs:
        if memory.memory_item_id in feedback_ids:
            continue
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

    # This conservative detector handles only explicit opposite preferences.
    # Other potential contradictions stay separate claims; the model must not
    # invent a resolved change from unrelated events or speaker-ambiguous text.
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
        )
        session.add(snapshot)
    elif (snapshot.source_memory_ids != source_ids or snapshot.domains != domains
          or snapshot.calibration_updates != calibration_updates):
        snapshot.revision += 1
        snapshot.source_memory_ids = source_ids
        snapshot.domains = domains
        snapshot.calibration_updates = calibration_updates
        snapshot.updated_at = utcnow()
    return snapshot
