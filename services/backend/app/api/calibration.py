"""Provisional Phase 3 calibration: lock the Twin answer before human input.

These records are Actor-submitted. No Subject identity proof exists in the
current account model, so feedback is never promoted to Subject evidence here.
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import CalibrationConflict, CalibrationNotFound, RequestInvalid
from ..models import Actor, CalibrationSession, as_utc, utcnow
from ..security import current_actor
from .core_twin import TwinQuestion, query_twin

router = APIRouter(prefix="/api/v1/subjects/{subject_id}/calibrations", tags=["calibration"])


class DimensionGaps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: bool
    reasoning: bool
    value_priority: bool
    emotional_reaction: bool
    expression: bool


class CalibrationAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    human_answer: str = Field(min_length=1, max_length=5000)
    gaps: DimensionGaps


class CalibrationView(BaseModel):
    calibration_id: str
    subject_id: str
    question: str
    locked_answer: str
    response_type: str
    confidence: float
    model_version: str | None
    evidence_ids: list[str]
    human_answer: str | None
    gaps: DimensionGaps | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def of(cls, row: CalibrationSession) -> "CalibrationView":
        return cls(
            calibration_id=row.calibration_id,
            subject_id=row.subject_id,
            question=row.question,
            locked_answer=row.locked_answer,
            response_type=row.response_type,
            confidence=row.confidence,
            model_version=row.model_version,
            evidence_ids=row.evidence_ids,
            human_answer=row.human_answer,
            gaps=DimensionGaps.model_validate(row.dimension_gaps) if row.dimension_gaps else None,
            created_at=as_utc(row.created_at),
            completed_at=as_utc(row.completed_at) if row.completed_at else None,
        )


def _owned(
    session: Session, *, subject_id: str, calibration_id: str, actor_id: str
) -> CalibrationSession:
    row = session.scalar(
        select(CalibrationSession).where(
            CalibrationSession.calibration_id == calibration_id,
            CalibrationSession.subject_id == subject_id,
            CalibrationSession.actor_id == actor_id,
        )
    )
    if row is None:
        raise CalibrationNotFound("No accessible Calibration")
    return row


@router.post("", response_model=CalibrationView, status_code=status.HTTP_201_CREATED)
def start_calibration(
    subject_id: str,
    payload: TwinQuestion,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> CalibrationView:
    # Query verifies this Actor's active independent CLOUD_TWIN consent.
    locked = query_twin(subject_id, payload, actor, session)
    row = CalibrationSession(
        calibration_id=f"cal_{uuid4().hex[:16]}",
        subject_id=subject_id,
        actor_id=actor.actor_id,
        cloud_twin_consent_id=payload.cloud_twin_consent_id,
        question=payload.question,
        locked_answer=locked.answer,
        response_type=locked.response_type,
        confidence=locked.confidence,
        model_version=locked.model_version,
        evidence_ids=[source.evidence_id for source in locked.evidence],
        created_at=utcnow(),
    )
    session.add(row)
    session.commit()
    return CalibrationView.of(row)


@router.get("", response_model=list[CalibrationView])
def list_calibrations(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> list[CalibrationView]:
    rows = session.scalars(
        select(CalibrationSession).where(
            CalibrationSession.subject_id == subject_id,
            CalibrationSession.actor_id == actor.actor_id,
        ).order_by(CalibrationSession.created_at.desc()).limit(100)
    ).all()
    return [CalibrationView.of(row) for row in rows]


@router.post("/{calibration_id}/answer", response_model=CalibrationView)
def answer_calibration(
    subject_id: str,
    calibration_id: str,
    payload: CalibrationAnswerRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> CalibrationView:
    row = _owned(
        session, subject_id=subject_id, calibration_id=calibration_id,
        actor_id=actor.actor_id,
    )
    answer = payload.human_answer.strip()
    if not answer:
        raise RequestInvalid("human_answer must contain text")
    gaps = payload.gaps.model_dump()
    if row.completed_at is not None:
        if row.human_answer == answer and row.dimension_gaps == gaps:
            return CalibrationView.of(row)
        raise CalibrationConflict("A locked calibration cannot be changed after submission")
    row.human_answer = answer
    row.dimension_gaps = gaps
    row.completed_at = utcnow()
    session.commit()
    return CalibrationView.of(row)
