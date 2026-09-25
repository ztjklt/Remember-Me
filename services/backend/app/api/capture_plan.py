"""Heuristic guided-capture question ranking over the Person Model preview."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domains import DOMAINS
from ..errors import SubjectNotFound
from ..models import Actor, CalibrationSession, PersonModelSnapshot
from ..security import current_actor
from .core_twin import _can_read_subject

router = APIRouter(prefix="/api/v1/subjects", tags=["capture-plan"])

QUESTIONS = {
    "Identity": "有哪些经历最能说明你是谁？",
    "Episodic Memory": "最近哪件事对你特别重要？",
    "Relationships": "谁对你影响最大？为什么？",
    "Preferences": "有什么习惯或偏好一直伴随你？",
    "Values & Beliefs": "遇到困难时你最坚持什么原则？",
    "Decision Patterns": "做重要决定时你通常先考虑什么？",
    "Expression": "你希望别人怎样理解你的说话方式？",
}
IMPORTANCE = {
    "Identity": 1.0,
    "Episodic Memory": 1.0,
    "Relationships": 1.2,
    "Preferences": 0.9,
    "Values & Beliefs": 1.2,
    "Decision Patterns": 1.15,
    "Expression": 0.9,
}
GAP_DOMAINS = {
    "decision": "Decision Patterns",
    "reasoning": "Decision Patterns",
    "value_priority": "Values & Beliefs",
    "emotional_reaction": "Relationships",
    "expression": "Expression",
}


class CaptureQuestion(BaseModel):
    domain: str
    question: str
    existing_facts: int
    information_gain: float
    importance: float
    uncertainty: float
    time_urgency: float
    interaction_cost: float
    score: float


class CapturePlan(BaseModel):
    subject_id: str
    model_version: str
    planning_method: str
    questions: list[CaptureQuestion]


@router.get("/{subject_id}/capture-plan", response_model=CapturePlan)
def capture_plan(
    subject_id: str,
    limit: int = Query(default=4, ge=2, le=4),
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> CapturePlan:
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    latest = session.scalar(
        select(CalibrationSession).where(
            CalibrationSession.subject_id == subject_id,
            CalibrationSession.actor_id == actor.actor_id,
            CalibrationSession.completed_at.is_not(None),
        ).order_by(CalibrationSession.completed_at.desc()).limit(1)
    )
    gaps = latest.dimension_gaps if latest and latest.dimension_gaps else {}
    urgent_domains = {
        domain for gap, domain in GAP_DOMAINS.items() if gaps.get(gap)
    }
    comparison = latest.ai_assessment if latest and latest.ai_assessment else {}
    urgent_domains.update(
        domain for gap, domain in GAP_DOMAINS.items()
        if comparison.get(gap, {}).get("verdict") == "DIFFERENT"
    )
    options: list[CaptureQuestion] = []
    for domain in DOMAINS:
        facts = snapshot.domains.get(domain, []) if snapshot else []
        count = len(facts)
        information_gain = 1.0 / (1 + count)
        importance = IMPORTANCE[domain]
        average_confidence = (
            sum(fact["confidence"] for fact in facts) / count if count else 0.0
        )
        uncertainty = 1.0 if count == 0 else max(0.2, 1.0 - average_confidence)
        time_urgency = 1.5 if domain in urgent_domains else 1.0
        question = QUESTIONS[domain]
        interaction_cost = 1.0 + max(0, len(question) - 20) / 100.0
        score = (
            information_gain * importance * uncertainty * time_urgency
            / interaction_cost
        )
        options.append(CaptureQuestion(
            domain=domain, question=question, existing_facts=count,
            information_gain=round(information_gain, 3),
            importance=importance, uncertainty=round(uncertainty, 3),
            time_urgency=time_urgency, interaction_cost=round(interaction_cost, 3),
            score=round(score, 3),
        ))
    options.sort(key=lambda item: (-item.score, item.domain))
    return CapturePlan(
        subject_id=subject_id,
        model_version=f"person-preview-r{snapshot.revision if snapshot else 0}",
        planning_method="heuristic-v2",
        questions=options[:limit],
    )
