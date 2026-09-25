"""Guided capture from the real temporal model, with an offline fixture path."""

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..domains import DOMAINS
from ..errors import AiFailed, AiSchemaInvalid, AiTimeout, AiUnavailable, SubjectNotFound
from ..models import Actor, CalibrationSession, Consent, PersonModelSnapshot
from ..person_model import rebuild_person_model
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
    followups: list[str] = []
    rationale: str | None = None


class CapturePlan(BaseModel):
    subject_id: str
    model_version: str
    planning_method: str
    questions: list[CaptureQuestion]


class _GeneratedQuestion(BaseModel):
    domain: str
    question: str = Field(min_length=5)
    followups: list[str] = Field(min_length=1, max_length=2)
    rationale: str
    information_gain: float = Field(ge=0.1, le=2)
    importance: float = Field(ge=0.1, le=2)
    uncertainty: float = Field(ge=0.1, le=2)
    time_urgency: float = Field(ge=0.1, le=2)
    interaction_cost: float = Field(ge=0.1, le=2)


class _GeneratedPlan(BaseModel):
    questions: list[_GeneratedQuestion] = Field(min_length=2, max_length=4)
    model_version: str = Field(min_length=1)
    planning_version: str = Field(min_length=1)


def _real_plan(
    subject_id: str, snapshot: PersonModelSnapshot | None,
    latest: CalibrationSession | None, limit: int, settings,
) -> CapturePlan:
    domains = snapshot.domains if snapshot else {}
    traits = [{
        "domain": domain, "statement": fact["content"],
        "confidence": fact["confidence"], "status": fact.get("status", "current"),
        "conflict_type": fact.get("conflict_type"),
    } for domain, facts in domains.items() if domain in DOMAINS for fact in facts]
    calibrations = [{
        "question": row["question"], "human_answer": row["human_answer"],
        "domains": [domain for domain in row["domains"] if domain in DOMAINS],
    } for row in (snapshot.calibration_updates if snapshot else [])[-10:]]
    if latest and latest.human_answer and not any(
        row["question"] == latest.question for row in calibrations
    ):
        gaps = latest.dimension_gaps or {}
        assessment = latest.ai_assessment or {}
        gap_domains = sorted({
            domain for dimension, domain in GAP_DOMAINS.items()
            if gaps.get(dimension) or assessment.get(dimension, {}).get("verdict") == "DIFFERENT"
        })
        calibrations.append({"question": latest.question,
                             "human_answer": latest.human_answer,
                             "domains": gap_domains})
    payload = {
        "coverage": {domain: len(domains.get(domain, [])) for domain in DOMAINS},
        "traits": traits[:100], "calibrations": calibrations, "limit": limit,
    }
    if len(traits) > 100:
        raise AiUnavailable("Capture Planner trait corpus exceeds its semantic window")
    try:
        response = httpx.post(
            settings.ai_core_url.rstrip("/") + "/capture/plan",
            json=payload, timeout=httpx.Timeout(settings.ai_timeout_seconds),
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise AiTimeout("Capture Planner timed out") from exc
    except httpx.TransportError as exc:
        raise AiUnavailable("Capture Planner unavailable") from exc
    if response.status_code in {408, 504}:
        raise AiTimeout("Capture Planner timed out")
    if response.status_code in {429, 503}:
        raise AiUnavailable("Capture Planner unavailable")
    if not response.is_success:
        raise AiFailed("Capture Planner failed")
    try:
        generated = _GeneratedPlan.model_validate(response.json())
    except (ValueError, TypeError) as exc:
        raise AiSchemaInvalid("Capture Planner violated its response schema") from exc
    if (generated.model_version.startswith(("fixture-", "fake-"))
            or generated.planning_version != "capture-planner-llm-v1"
            or len(generated.questions) > limit):
        raise AiSchemaInvalid("Capture Planner returned an unversioned or oversized plan")
    questions = []
    seen = set()
    for item in generated.questions:
        if item.domain not in DOMAINS or item.question.strip().casefold() in seen:
            raise AiSchemaInvalid("Capture Planner repeated a question or invented a domain")
        seen.add(item.question.strip().casefold())
        questions.append(CaptureQuestion(
            domain=item.domain, question=item.question,
            existing_facts=len(domains.get(item.domain, [])),
            information_gain=item.information_gain, importance=item.importance,
            uncertainty=item.uncertainty, time_urgency=item.time_urgency,
            interaction_cost=item.interaction_cost,
            score=round(item.information_gain * item.importance * item.uncertainty
                        * item.time_urgency / item.interaction_cost, 3),
            followups=item.followups, rationale=item.rationale,
        ))
    questions.sort(key=lambda item: -item.score)
    return CapturePlan(
        subject_id=subject_id, model_version=generated.model_version,
        planning_method=generated.planning_version, questions=questions,
    )


@router.get("/{subject_id}/capture-plan", response_model=CapturePlan)
def capture_plan(
    subject_id: str,
    request: Request,
    limit: int = Query(default=4, ge=2, le=4),
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> CapturePlan:
    if not _can_read_subject(session, subject_id=subject_id, actor_id=actor.actor_id):
        raise SubjectNotFound("No accessible Subject")
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    if (request.app.state.settings.ai_backend == "http"
            and (snapshot is None or snapshot.synthesis_model_version is None)):
        snapshot = rebuild_person_model(
            session, subject_id=subject_id, actor_id=actor.actor_id,
            settings=request.app.state.settings,
        )
        session.commit()
    latest = session.scalar(
        select(CalibrationSession).join(
            Consent, CalibrationSession.cloud_twin_consent_id == Consent.consent_id
        ).where(
            CalibrationSession.subject_id == subject_id,
            CalibrationSession.actor_id == actor.actor_id,
            CalibrationSession.confirmed_at.is_not(None),
            Consent.status == "granted",
        ).order_by(CalibrationSession.completed_at.desc()).limit(1)
    )
    if request.app.state.settings.ai_backend == "http":
        return _real_plan(subject_id, snapshot, latest, limit, request.app.state.settings)
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
    followup_domain = sorted(urgent_domains)[0] if urgent_domains else None
    followup_text = None
    if latest and latest.human_answer and followup_domain:
        excerpt = " ".join(latest.human_answer.split())[:40]
        followup_text = f"你刚才提到“{excerpt}”，能讲讲一件具体经历吗？"
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
        question = followup_text if domain == followup_domain and followup_text else QUESTIONS[domain]
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
        planning_method="heuristic-v3-contextual" if followup_text else "heuristic-v2",
        questions=options[:limit],
    )
