"""Deterministic, provenance-preserving Person Model preview materialization.

No unsupported trait is synthesized. The snapshot records which available
Memory claims support each domain and can be rebuilt after feedback/deletion.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domains import DOMAINS, MEMORY_DOMAIN
from .models import (
    Episode, MemoryFeedback, MemoryItem, PersonModelSnapshot, as_utc, utcnow,
)


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
        })
        source_ids.append(memory.memory_item_id)

    snapshot = session.get(PersonModelSnapshot, (subject_id, actor_id))
    if snapshot is None:
        snapshot = PersonModelSnapshot(
            subject_id=subject_id, actor_id=actor_id, revision=1,
            source_memory_ids=source_ids, domains=domains, updated_at=utcnow(),
        )
        session.add(snapshot)
    elif snapshot.source_memory_ids != source_ids or snapshot.domains != domains:
        snapshot.revision += 1
        snapshot.source_memory_ids = source_ids
        snapshot.domains = domains
        snapshot.updated_at = utcnow()
    return snapshot
