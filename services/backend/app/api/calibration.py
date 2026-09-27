"""Locked-answer calibration tied to a later, confirmed human Episode."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..calibration_client import CalibrationUnavailable
from ..db import get_session
from ..errors import AppError
from ..models import (Actor, CalibrationRun, ConsentScope, Episode, Evidence,
                      MemoryItem, TwinAnswer, utcnow)
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from .twin import require_subject

router = APIRouter(prefix="/api/v1/subjects/{subject_id}/calibrations", tags=["calibration"])
DIMENSIONS = {"DECISION", "REASONING", "VALUE_PRIORITY", "EMOTIONAL_REACTION", "EXPRESSION"}
ALIGNMENTS = {"MATCH", "PARTIAL", "DIFFERENT", "NOT_OBSERVED"}


class CalibrationNotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class CalibrationNotReady(AppError):
    code = "CALIBRATION_NOT_READY"
    http_status = 409


class CalibrationFailed(AppError):
    code = "CALIBRATION_UNAVAILABLE"
    http_status = 503


class StartCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    twin_answer_id: str = Field(min_length=1)
    cloud_consent_id: str = Field(min_length=1)


class CompleteCalibration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cloud_consent_id: str = Field(min_length=1)


def _snapshot(session: Session, subject_id: str, memory_ids: list[str]) -> list[dict] | None:
    snapshot = []
    for identifier in sorted(set(memory_ids)):
        item = session.get(MemoryItem, identifier)
        if item is None or item.deleted_at is not None:
            return None
        episode = session.get(Episode, item.episode_id)
        if episode is None or episode.subject_id != subject_id:
            return None
        snapshot.append({"memory_item_id": identifier, "content": item.content,
                         "evidence_ids": item.evidence_ids})
    return snapshot


def _run(session: Session, subject_id: str, actor: Actor, calibration_id: str) -> CalibrationRun:
    row = session.scalar(select(CalibrationRun).where(
        CalibrationRun.calibration_id == calibration_id,
        CalibrationRun.subject_id == subject_id, CalibrationRun.actor_id == actor.actor_id))
    if row is None:
        raise CalibrationNotFound("校准不存在。")
    return row


def _check_source(session: Session, row: CalibrationRun) -> bool:
    ids = [item["memory_item_id"] for item in row.source_snapshot]
    if _snapshot(session, row.subject_id, ids) != row.source_snapshot:
        row.status = "stale"
        return False
    for identifier in row.locked_evidence_ids:
        evidence = session.get(Evidence, identifier)
        if evidence is None:
            row.status = "stale"
            return False
    return True


def _view(row: CalibrationRun) -> dict:
    stale = row.status == "stale"
    return {
        "calibration_id": row.calibration_id, "subject_id": row.subject_id,
        "twin_answer_id": row.twin_answer_id, "question": row.question,
        "locked_answer": None if stale else row.locked_answer,
        "locked_response_type": row.locked_response_type,
        "locked_model_version": row.locked_model_version,
        "locked_person_model_version": row.locked_person_model_version,
        "locked_evidence_ids": [] if stale else row.locked_evidence_ids,
        "status": row.status, "human_episode_id": row.human_episode_id,
        "summary": None if stale else row.summary,
        "dimensions": [] if stale else row.dimension_diffs,
        "suggested_question": None if stale else row.suggested_question,
        "comparison_model_version": row.comparison_model_version,
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.post("")
def start(subject_id: str, body: StartCalibration,
          actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(body.cloud_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.CLOUD_TWIN, actor_id=actor.actor_id)
    answer = session.scalar(select(TwinAnswer).where(
        TwinAnswer.answer_id == body.twin_answer_id, TwinAnswer.subject_id == subject_id,
        TwinAnswer.actor_id == actor.actor_id))
    if answer is None or answer.invalidated_at is not None or answer.response_type == "UNKNOWN":
        raise CalibrationNotReady("请先取得一条未过期且有证据的 Twin 回答。")
    existing = session.scalar(select(CalibrationRun).where(CalibrationRun.twin_answer_id == answer.answer_id))
    if existing is not None:
        _check_source(session, existing)
        session.commit()
        return _view(existing)
    snapshot = _snapshot(session, subject_id, answer.memory_item_ids)
    if not snapshot or not answer.evidence_ids:
        raise CalibrationNotReady("Twin 回答缺少有效的原始记忆证据。")
    row = CalibrationRun(
        calibration_id="cal_" + uuid4().hex[:16], subject_id=subject_id,
        actor_id=actor.actor_id, twin_answer_id=answer.answer_id,
        question=answer.question, locked_answer=answer.answer,
        locked_response_type=answer.response_type,
        locked_model_version=answer.model_version,
        locked_person_model_version=answer.person_model_version,
        locked_evidence_ids=answer.evidence_ids, source_snapshot=snapshot,
        status="awaiting_human", dimension_diffs=[], created_at=utcnow(),
    )
    session.add(row)
    session.commit()
    return _view(row)


@router.get("")
def list_runs(subject_id: str, actor: Actor = Depends(current_actor),
              session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    rows = list(session.scalars(select(CalibrationRun).where(
        CalibrationRun.subject_id == subject_id, CalibrationRun.actor_id == actor.actor_id)
        .order_by(CalibrationRun.created_at.desc()).limit(20)))
    for row in rows:
        if row.status != "stale":
            _check_source(session, row)
    session.commit()
    return {"items": [_view(row) for row in rows]}


@router.get("/{calibration_id}")
def read(subject_id: str, calibration_id: str, actor: Actor = Depends(current_actor),
         session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    row = _run(session, subject_id, actor, calibration_id)
    if row.status != "stale":
        _check_source(session, row)
        session.commit()
    return _view(row)


@router.post("/{calibration_id}/complete")
def complete(subject_id: str, calibration_id: str, body: CompleteCalibration, request: Request,
             actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    require_subject(session, subject_id, actor)
    ConsentRepository(session).require_active(body.cloud_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.CLOUD_TWIN, actor_id=actor.actor_id)
    row = _run(session, subject_id, actor, calibration_id)
    if row.status != "stale" and not _check_source(session, row):
        session.commit()
        raise CalibrationNotReady("原始证据已有变化，请重新获取 Twin 回答。")
    if row.status == "complete":
        return _view(row)
    if row.status == "stale":
        raise CalibrationNotReady("原始证据已有变化，请重新获取 Twin 回答。")
    episode = session.get(Episode, row.human_episode_id) if row.human_episode_id else None
    if (episode is None or episode.subject_id != subject_id or episode.actor_id != actor.actor_id
            or (episode.capture_metadata or {}).get("calibration_id") != calibration_id
            or episode.status != "ready" or episode.transcript_reviewed_at is None
            or not episode.transcript):
        raise CalibrationNotReady("请先录下本人回答，核对文字并等待记忆处理完成。")
    question, locked_answer, human_answer = row.question, row.locked_answer, episode.transcript
    if request.app.state.settings.ai_backend != "http":
        raise CalibrationFailed("请先连接真实的 AI Core 服务。")
    session.commit()
    try:
        result = request.app.state.calibration_client.compare(question, locked_answer, human_answer)
    except CalibrationUnavailable as exc:
        raise CalibrationFailed(str(exc)) from exc
    dimensions = result.get("dimensions")
    version = result.get("model_version")
    summary = result.get("summary")
    suggested = result.get("suggested_question")
    if (not isinstance(dimensions, list) or len(dimensions) != 5
            or not isinstance(version, str) or not version or len(version) > 128
            or not isinstance(summary, str) or not summary.strip() or len(summary) > 400
            or suggested is not None and (not isinstance(suggested, str) or len(suggested) > 200)):
        raise CalibrationFailed("模型校准结果格式不正确。")
    seen = set()
    for item in dimensions:
        if not isinstance(item, dict):
            raise CalibrationFailed("模型校准维度格式不正确。")
        dimension, alignment = item.get("dimension"), item.get("alignment")
        note, excerpt = item.get("note"), item.get("human_excerpt")
        if (dimension not in DIMENSIONS or dimension in seen or alignment not in ALIGNMENTS
                or not isinstance(note, str) or not note.strip() or len(note) > 250
                or (alignment == "NOT_OBSERVED" and excerpt is not None)
                or (alignment != "NOT_OBSERVED" and
                    (not isinstance(excerpt, str) or not excerpt or len(excerpt) > 500
                     or excerpt not in human_answer))):
            raise CalibrationFailed("模型校准证据无法核对。")
        seen.add(dimension)
    session.expire_all()
    row = _run(session, subject_id, actor, calibration_id)
    ConsentRepository(session).require_active(body.cloud_consent_id, subject_id=subject_id,
                                               scope=ConsentScope.CLOUD_TWIN, actor_id=actor.actor_id)
    if row.status != "awaiting_human" or not _check_source(session, row):
        raise CalibrationNotReady("校准所依据的内容已变化。")
    current_episode = session.get(Episode, row.human_episode_id)
    if current_episode is None or current_episode.status != "ready" or current_episode.transcript != human_answer:
        raise CalibrationNotReady("本人回答已变化，请重新查看。")
    row.status = "complete"
    row.summary = summary
    row.dimension_diffs = dimensions
    row.suggested_question = suggested
    row.comparison_model_version = version
    row.completed_at = utcnow()
    session.commit()
    return _view(row)
