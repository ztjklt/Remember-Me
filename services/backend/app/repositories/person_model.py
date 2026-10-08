"""Rebuild derived person model from the subject's active, auditable memories."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    CaptureQuestion, Episode, Evidence, GraphFact, MemoryItem, ModelRevision,
    PERSON_DOMAINS, PersonTrait, as_utc,
)

DOMAIN_FOR_TYPE = {
    "EVENT": "EPISODIC_MEMORY", "PERSON": "IDENTITY",
    "RELATIONSHIP": "RELATIONSHIPS", "PREFERENCE": "PREFERENCES",
    "VALUE": "VALUES_BELIEFS", "EMOTION": "EPISODIC_MEMORY",
}

from ..capture_planner import QUESTIONS, plan


def _contradicts(left: str, right: str) -> bool:
    """Conservative explicit-negation check; uncertain conflicts remain separate."""
    def normalize(value: str) -> tuple[str, bool]:
        compact = "".join(value.split()).strip("。！!？?")
        negative = any(token in compact for token in ("不喜欢", "不爱", "讨厌", "不想", "不会", "没有", "不是"))
        for token in ("不喜欢", "不爱", "讨厌", "不想", "不会", "没有", "不是"):
            compact = compact.replace(token, "喜欢" if token in ("不喜欢", "不爱", "讨厌") else "")
        return compact, negative
    a, neg_a = normalize(left)
    b, neg_b = normalize(right)
    return bool(a and a == b and neg_a != neg_b)


class PersonModelRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def rebuild(self, subject_id: str, *, answered_question_id: str | None = None) -> int:
        session = self.session
        # IDs belong to durable Memory records, not a model-generated proposal.
        # Preserve existing IDs (including those made by older deployments) when
        # rebuilding after a correction or an unrelated new Episode.
        previous_traits = {
            memory_id: row.trait_id
            for row in session.scalars(select(PersonTrait).where(PersonTrait.subject_id == subject_id))
            for memory_id in row.memory_item_ids[:1]
        }
        previous_facts = {
            memory_id: row.fact_id
            for row in session.scalars(select(GraphFact).where(GraphFact.subject_id == subject_id))
            for memory_id in row.memory_item_ids[:1]
        }
        if answered_question_id:
            question = session.get(CaptureQuestion, answered_question_id)
            if question and question.subject_id == subject_id:
                question.status = "answered"

        # Memory rows and evidence are historical source records. Only derived
        # tables are replaced; a correction/deletion can thus be recomputed.
        session.execute(delete(PersonTrait).where(PersonTrait.subject_id == subject_id))
        session.execute(delete(GraphFact).where(GraphFact.subject_id == subject_id))
        memories = list(session.execute(
            select(MemoryItem, Episode).join(Episode).where(
                Episode.subject_id == subject_id, MemoryItem.deleted_at.is_(None)
            ).order_by(Episode.created_at, MemoryItem.ordinal)
        ).all())
        traits: list[PersonTrait] = []
        for memory, episode in memories:
            proposals = episode.model_proposals or {}
            # The AI Core proposal is the authority for the initial domain and
            # trait, linked by both statement and verified evidence. A human
            # correction gets new CALIBRATION evidence and is rebuilt from the
            # corrected Memory instead of reviving the older AI proposal.
            proposal = next((item for item in proposals.get("persona_updates", [])
                             if item.get("statement") == memory.content
                             and set(item.get("evidence_ids", [])) & set(memory.evidence_ids)), None)
            metadata = memory.item_metadata or {}
            domain = metadata.get("domain") or (proposal or {}).get("domain") or DOMAIN_FOR_TYPE[memory.memory_type]
            if domain not in PERSON_DOMAINS:
                domain = DOMAIN_FOR_TYPE[memory.memory_type]
            evidence = session.get(Evidence, memory.evidence_ids[0]) if memory.evidence_ids else None
            sources = [session.get(Evidence, eid) for eid in memory.evidence_ids]
            if not sources or any(source is None or source.source_type not in {"SUBJECT", "CALIBRATION"} for source in sources):
                continue  # Retain third-party memories, never promote them to Subject traits.
            reflection = (memory.item_metadata or {}).get("reflection", {})
            if reflection.get("input_statement") != memory.content:
                reflection = {}
            trait = PersonTrait(
                trait_id=previous_traits.get(memory.memory_item_id) or "trait_" + memory.memory_item_id,
                subject_id=subject_id, domain=domain, statement=memory.content,
                context=reflection.get("context") if reflection else (proposal or {}).get("context") or (evidence.excerpt if evidence else None),
                confidence=memory.confidence, source_type=memory.source_type,
                evidence_ids=list(memory.evidence_ids), counter_evidence_ids=[],
                memory_item_ids=[memory.memory_item_id], status="active",
                model_version=memory.model_version, valid_from=memory.effective_at,
            )
            snapshot = reflection.get("target") or {}
            target = next((old for old in traits if old.status != "superseded"
                           and old.domain == domain and old.statement == snapshot.get("statement")
                           and old.context == snapshot.get("context")
                           and snapshot.get("memory_item_ids")
                           and set(snapshot["memory_item_ids"]) <= set(old.memory_item_ids)
                           and set(snapshot.get("evidence_ids", [])) <= set(old.evidence_ids)), None)
            action = reflection.get("action") if target else "ADD"
            if action == "SUPPORT" and _contradicts(target.statement, trait.statement):
                action = "CONFLICT"
            if action == "SUPPORT":
                previous_episodes = {m.episode_id for m, _ in memories if m.memory_item_id in target.memory_item_ids}
                target.evidence_ids = sorted(set(target.evidence_ids + trait.evidence_ids))
                target.memory_item_ids = list(dict.fromkeys(target.memory_item_ids + trait.memory_item_ids))
                # Repeat snippets from one episode do not establish a stable pattern.
                independent = {m.episode_id for m, _ in memories if m.memory_item_id in target.memory_item_ids}
                if len(independent) >= 2 and episode.episode_id not in previous_episodes:
                    target.confidence = min(.85, 1 - (1 - target.confidence) * (1 - trait.confidence))
                elif len(independent) < 2:
                    target.confidence = min(.65, target.confidence)
                target.model_version = trait.model_version
            else:
                if action in {"CONFLICT", "CHANGE"}:
                    previous_counter = list(target.counter_evidence_ids)
                    target.counter_evidence_ids = sorted(set(target.counter_evidence_ids + trait.evidence_ids))
                    trait.counter_evidence_ids = list(target.evidence_ids)
                    if action == "CHANGE":
                        target.status = "superseded"
                        target.valid_to = memory.effective_at or episode.recorded_at
                        # A clarification of a conflicted target also retires
                        # its directly linked alternatives in the same context.
                        for peer in traits:
                            if (peer is not target and peer.status == "unresolved" and peer.domain == target.domain
                                    and peer.context == target.context and set(peer.evidence_ids) & set(previous_counter)):
                                peer.status = "superseded"
                                peer.valid_to = memory.effective_at or episode.recorded_at
                                peer.counter_evidence_ids = sorted(set(peer.counter_evidence_ids + trait.evidence_ids))
                                trait.counter_evidence_ids = sorted(set(trait.counter_evidence_ids + peer.evidence_ids))
                    else:
                        target.status = trait.status = "unresolved"
                        target.confidence = min(target.confidence, .5)
                        trait.confidence = min(trait.confidence, .5)
                elif not reflection or (target is None and reflection.get("action") != "ADD"):
                    for old in traits:
                        if old.status != "superseded" and old.domain == domain and _contradicts(old.statement, trait.statement):
                            old.status = trait.status = "unresolved"
                            old.counter_evidence_ids = sorted(set(old.counter_evidence_ids + trait.evidence_ids))
                            trait.counter_evidence_ids = sorted(set(trait.counter_evidence_ids + old.evidence_ids))
                traits.append(trait)
            if memory.memory_type in {"EVENT", "PERSON", "RELATIONSHIP"}:
                fact_proposal = next((item for item in proposals.get("graph_updates", [])
                                      if item.get("content") == memory.content
                                      and set(item.get("evidence_ids", [])) & set(memory.evidence_ids)), None)
                session.add(GraphFact(
                    fact_id=previous_facts.get(memory.memory_item_id) or "fact_" + memory.memory_item_id,
                    subject_id=subject_id, kind=(fact_proposal or {}).get("kind") or memory.memory_type,
                    content=memory.content, evidence_ids=list(memory.evidence_ids),
                    memory_item_ids=[memory.memory_item_id],
                    model_version=memory.model_version, valid_from=memory.effective_at,
                ))
        session.add_all(traits)

        version = session.get(ModelRevision, subject_id)
        if version is None:
            version = ModelRevision(subject_id=subject_id, version=0)
            session.add(version)
        version.version += 1

        plan(session, subject_id)
        return version.version
