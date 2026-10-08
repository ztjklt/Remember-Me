"""Rebuild derived person model from the subject's active, auditable memories."""

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    CaptureQuestion, Episode, Evidence, GraphFact, MemoryItem, ModelRevision,
    PERSON_DOMAINS, PersonTrait, utcnow,
)

DOMAIN_FOR_TYPE = {
    "EVENT": "EPISODIC_MEMORY", "PERSON": "IDENTITY",
    "RELATIONSHIP": "RELATIONSHIPS", "PREFERENCE": "PREFERENCES",
    "VALUE": "VALUES_BELIEFS", "EMOTION": "EPISODIC_MEMORY",
}

QUESTIONS = {
    "IDENTITY": "你会怎样向一个刚认识的人介绍自己？可以从一段经历说起。",
    "EPISODIC_MEMORY": "讲一段对你影响很大的经历吧。当时发生了什么？",
    "RELATIONSHIPS": "选一个对你很重要的人，讲一件你们一起经历的事吧。",
    "PREFERENCES": "最近有什么让你觉得特别舒服或不舒服？可以讲一个具体例子。",
    "VALUES_BELIEFS": "讲一次你不得不取舍的经历吧。当时你最看重什么？",
    "DECISION_PATTERNS": "最近一个难做的决定是什么？你最后是怎么决定的？",
    "EXPRESSION": "别人用什么方式跟你交流时，你会觉得被理解？可以举一个例子。",
}


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
            domain = (proposal or {}).get("domain") or (memory.item_metadata or {}).get("domain") or DOMAIN_FOR_TYPE[memory.memory_type]
            if domain not in PERSON_DOMAINS:
                domain = DOMAIN_FOR_TYPE[memory.memory_type]
            evidence = session.get(Evidence, memory.evidence_ids[0]) if memory.evidence_ids else None
            trait = PersonTrait(
                trait_id=(proposal or {}).get("trait_id") or "trait_" + memory.memory_item_id,
                subject_id=subject_id, domain=domain, statement=memory.content,
                context=(proposal or {}).get("context") or (evidence.excerpt if evidence else None),
                confidence=memory.confidence, source_type=memory.source_type,
                evidence_ids=list(memory.evidence_ids), counter_evidence_ids=[],
                memory_item_ids=[memory.memory_item_id], status="active",
                model_version=memory.model_version, valid_from=memory.effective_at,
            )
            for old in traits:
                if old.domain == domain and _contradicts(old.statement, trait.statement):
                    old.status = trait.status = "unresolved"
                    old.counter_evidence_ids = sorted(set(old.counter_evidence_ids + trait.evidence_ids))
                    trait.counter_evidence_ids = sorted(set(trait.counter_evidence_ids + old.evidence_ids))
            traits.append(trait)
            if memory.memory_type in {"EVENT", "PERSON", "RELATIONSHIP"}:
                fact_proposal = next((item for item in proposals.get("graph_updates", [])
                                      if item.get("content") == memory.content
                                      and set(item.get("evidence_ids", [])) & set(memory.evidence_ids)), None)
                session.add(GraphFact(
                    fact_id=(fact_proposal or {}).get("fact_id") or "fact_" + memory.memory_item_id,
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

        pending = list(session.scalars(select(CaptureQuestion).where(
            CaptureQuestion.subject_id == subject_id, CaptureQuestion.status == "pending"
        )))
        for question in pending:
            question.status = "skipped"
        unresolved = next((trait for trait in traits if trait.status == "unresolved"), None)
        if unresolved:
            domain = unresolved.domain
            text = f"关于「{unresolved.statement[:100]}」你有过不同说法。能讲讲各自发生在什么情境吗？"
            reason = "contradiction"
            evidence_ids = unresolved.evidence_ids + unresolved.counter_evidence_ids
        else:
            covered = {trait.domain for trait in traits}
            domain = next((name for name in PERSON_DOMAINS if name not in covered), None)
            text = QUESTIONS[domain] if domain else None
            reason = "missing_domain"
            evidence_ids = []
        if text and domain:
            session.add(CaptureQuestion(
                question_id="question_" + uuid4().hex[:16], subject_id=subject_id,
                text=text, target_domain=domain, reason=reason,
                evidence_ids=evidence_ids, status="pending", created_at=utcnow(),
            ))
        return version.version
