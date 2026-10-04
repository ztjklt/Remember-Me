"""Opt-in prototype routes, deliberately outside the frozen /api/v1 surface."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from remember_contracts.agent import (
    CalibrationSubmit,
    CalibrationView,
    GrantRequest,
    Material,
    Plan,
    QuestionRequest,
    Snapshot,
    TwinAnswer,
)
from ..agent_service import AgentService, AgentNotFound
from ..db import get_session
from ..models import Actor
from ..security import current_actor

router = APIRouter(
    prefix="/experimental/agent/v1/subjects/{subject_id}", tags=["experimental-agent"]
)


def service(request, session):
    return AgentService(session, request.app.state.agent_client)


@router.post("/grant")
def grant(
    subject_id: str,
    payload: GrantRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    return service(request, session).grant(subject_id, actor.actor_id, payload)


@router.delete("/grant", status_code=204)
def revoke(
    subject_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    svc.revoke(svc.require(subject_id, actor.actor_id))


@router.get("/model", response_model=Snapshot)
def model(
    subject_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.snapshot(svc.require(subject_id, actor.actor_id))


@router.post("/model/refresh", response_model=Snapshot)
def refresh(
    subject_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    result = svc.refresh(svc.require(subject_id, actor.actor_id))
    session.commit()
    return result


@router.get("/evidence", response_model=list[Material])
def evidence(
    subject_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.materials(svc.require(subject_id, actor.actor_id))


@router.get("/evidence/{evidence_id}", response_model=Material)
def read_evidence(
    subject_id: str,
    evidence_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    state = svc.require(subject_id, actor.actor_id)
    source = next(
        (m for m in svc.materials(state) if m.evidence_id == evidence_id), None
    )
    if source is None:
        raise AgentNotFound("Evidence not found")
    return source


@router.post("/twin", response_model=TwinAnswer)
def twin(
    subject_id: str,
    payload: QuestionRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.twin(svc.require(subject_id, actor.actor_id), payload.question)


@router.post("/calibrations", response_model=CalibrationView, status_code=201)
def lock(
    subject_id: str,
    payload: QuestionRequest,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.lock(svc.require(subject_id, actor.actor_id), payload.question)


@router.get("/calibrations/{calibration_id}", response_model=CalibrationView)
def read_calibration(
    subject_id: str,
    calibration_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.view(svc.record(svc.require(subject_id, actor.actor_id), calibration_id))


@router.post("/calibrations/{calibration_id}/submit", response_model=CalibrationView)
def submit(
    subject_id: str,
    calibration_id: str,
    payload: CalibrationSubmit,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    state = svc.require(subject_id, actor.actor_id)
    return svc.submit(state, svc.record(state, calibration_id), payload)


@router.get("/plan", response_model=Plan)
def plan(
    subject_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.plan(svc.require(subject_id, actor.actor_id))


@router.delete("/episodes/{episode_id}/use", response_model=Snapshot)
def withdraw(
    subject_id: str,
    episode_id: str,
    request: Request,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
):
    svc = service(request, session)
    return svc.withdraw_episode(svc.require(subject_id, actor.actor_id), episode_id)
