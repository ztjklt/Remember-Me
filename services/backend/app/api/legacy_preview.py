"""Revocable, domain-scoped recipient preview for the isolated iOS branch.

This is a manual rehearsal. It does not assert death, legal authority, Subject
identity verification, or production Legacy transition.
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import (
    LegacyAccessDenied, LegacyGrantConflict, LegacyGrantNotFound, RequestInvalid,
)
from ..models import (
    Actor, Consent, ConsentScope, ConsentStatus, Episode, LegacyAuditEvent,
    LegacyGrant, PersonModelSnapshot, as_utc, utcnow,
)
from ..repositories.consents import ConsentRepository
from ..security import current_actor
from .core_twin import DOMAINS, MemoryView, _memories

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["legacy-preview"])
ALLOWED_DOMAINS = set(DOMAINS) | {"Unclassified"}


class GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_actor_id: str = Field(min_length=1)
    handover_consent_id: str = Field(min_length=1)
    allowed_domains: list[str] = Field(min_length=1, max_length=8)


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str


class GrantView(BaseModel):
    grant_id: str
    subject_id: str
    recipient_actor_id: str
    allowed_domains: list[str]
    status: str
    snapshot_count: int
    baseline_model_revision: int | None
    created_at: datetime
    activated_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def of(cls, row: LegacyGrant) -> "GrantView":
        return cls(
            grant_id=row.grant_id, subject_id=row.subject_id,
            recipient_actor_id=row.recipient_actor_id,
            allowed_domains=row.allowed_domains, status=row.status,
            snapshot_count=len(row.snapshot_memory_ids),
            baseline_model_revision=row.baseline_model_revision,
            created_at=as_utc(row.created_at),
            activated_at=as_utc(row.activated_at) if row.activated_at else None,
            revoked_at=as_utc(row.revoked_at) if row.revoked_at else None,
        )


class RecipientMemories(BaseModel):
    subject_id: str
    mode: str
    items: list[MemoryView]


class AuditView(BaseModel):
    event_id: str
    grant_id: str
    actor_id: str
    action: str
    occurred_at: datetime

    @classmethod
    def of(cls, row: LegacyAuditEvent) -> "AuditView":
        return cls(
            event_id=row.event_id, grant_id=row.grant_id,
            actor_id=row.actor_id, action=row.action,
            occurred_at=as_utc(row.occurred_at),
        )


def _audit(session: Session, *, grant_id: str, actor_id: str, action: str) -> None:
    session.add(LegacyAuditEvent(
        event_id=f"audit_{uuid4().hex[:16]}", grant_id=grant_id,
        actor_id=actor_id, action=action, occurred_at=utcnow(),
    ))


def _own_grant(
    session: Session, *, subject_id: str, grant_id: str, actor_id: str
) -> LegacyGrant:
    row = session.scalar(
        select(LegacyGrant).where(
            LegacyGrant.grant_id == grant_id,
            LegacyGrant.subject_id == subject_id,
            LegacyGrant.grantor_actor_id == actor_id,
        )
    )
    if row is None:
        raise LegacyGrantNotFound("No accessible grant")
    return row


@router.post("/handover/grants", response_model=GrantView, status_code=status.HTTP_201_CREATED)
def create_grant(
    subject_id: str,
    payload: GrantRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> GrantView:
    ConsentRepository(session).require_active(
        payload.handover_consent_id,
        subject_id=subject_id, scope=ConsentScope.DIGITAL_HANDOVER,
        actor_id=actor.actor_id,
    )
    if payload.recipient_actor_id == actor.actor_id:
        raise RequestInvalid("Recipient must be a different Actor")
    if session.get(Actor, payload.recipient_actor_id) is None:
        raise RequestInvalid("Recipient Actor does not exist")
    domains = set(payload.allowed_domains)
    if len(domains) != len(payload.allowed_domains) or not domains <= ALLOWED_DOMAINS:
        raise RequestInvalid("allowed_domains must contain known unique domains")
    owned = session.scalar(
        select(Episode.episode_id).where(
            Episode.subject_id == subject_id,
            Episode.actor_id == actor.actor_id,
            Episode.status == "ready",
        ).limit(1)
    )
    if owned is None:
        raise LegacyAccessDenied("Grantor has no ready Episode for this Subject")
    row = LegacyGrant(
        grant_id=f"grant_{uuid4().hex[:16]}", subject_id=subject_id,
        grantor_actor_id=actor.actor_id,
        recipient_actor_id=payload.recipient_actor_id,
        handover_consent_id=payload.handover_consent_id,
        allowed_domains=sorted(domains), snapshot_memory_ids=[],
        status="DRAFT", created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    _audit(session, grant_id=row.grant_id, actor_id=actor.actor_id, action="CREATED")
    session.commit()
    return GrantView.of(row)


@router.get("/handover/grants", response_model=list[GrantView])
def list_grants(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> list[GrantView]:
    rows = session.scalars(
        select(LegacyGrant).where(
            LegacyGrant.subject_id == subject_id,
            LegacyGrant.grantor_actor_id == actor.actor_id,
        ).order_by(LegacyGrant.created_at.desc())
    ).all()
    return [GrantView.of(row) for row in rows]


@router.get("/handover/grants/{grant_id}/audit", response_model=list[AuditView])
def grant_audit(
    subject_id: str,
    grant_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> list[AuditView]:
    _own_grant(session, subject_id=subject_id, grant_id=grant_id, actor_id=actor.actor_id)
    rows = session.scalars(
        select(LegacyAuditEvent).where(LegacyAuditEvent.grant_id == grant_id)
        .order_by(LegacyAuditEvent.occurred_at, LegacyAuditEvent.event_id)
    ).all()
    return [AuditView.of(row) for row in rows]


@router.post("/handover/grants/{grant_id}/activate-preview", response_model=GrantView)
def activate_preview(
    subject_id: str,
    grant_id: str,
    payload: ActivateRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> GrantView:
    row = _own_grant(
        session, subject_id=subject_id, grant_id=grant_id, actor_id=actor.actor_id,
    )
    if row.status == "PREVIEW_ACTIVE":
        return GrantView.of(row)
    if row.status != "DRAFT":
        raise LegacyGrantConflict("A revoked grant cannot be activated")
    if payload.confirmation != "ACTIVATE_PREVIEW":
        raise RequestInvalid("Explicit preview activation confirmation is required")
    ConsentRepository(session).require_active(
        row.handover_consent_id,
        subject_id=subject_id, scope=ConsentScope.DIGITAL_HANDOVER,
        actor_id=actor.actor_id,
    )
    row.snapshot_memory_ids = [
        item.memory_item_id
        for item in _memories(session, subject_id=subject_id, actor_id=actor.actor_id)
        if item.domain in row.allowed_domains and item.correction is None
    ]
    if not row.snapshot_memory_ids:
        raise LegacyGrantConflict("No eligible Memory is available for this preview")
    row.status = "PREVIEW_ACTIVE"
    row.activated_at = utcnow()
    snapshot = session.get(PersonModelSnapshot, (subject_id, actor.actor_id))
    row.baseline_model_revision = snapshot.revision if snapshot else 0
    _audit(session, grant_id=row.grant_id, actor_id=actor.actor_id, action="ACTIVATED")
    session.commit()
    return GrantView.of(row)


@router.post("/handover/grants/{grant_id}/revoke", response_model=GrantView)
def revoke_grant(
    subject_id: str,
    grant_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> GrantView:
    row = _own_grant(
        session, subject_id=subject_id, grant_id=grant_id, actor_id=actor.actor_id,
    )
    if row.status != "REVOKED":
        row.status = "REVOKED"
        row.revoked_at = utcnow()
        _audit(session, grant_id=row.grant_id, actor_id=actor.actor_id, action="REVOKED")
        session.commit()
    return GrantView.of(row)


@router.get("/legacy-preview/memories", response_model=RecipientMemories)
def recipient_memories(
    subject_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> RecipientMemories:
    rows = session.scalars(
        select(LegacyGrant)
        .join(Consent, LegacyGrant.handover_consent_id == Consent.consent_id)
        .where(
            LegacyGrant.subject_id == subject_id,
            LegacyGrant.recipient_actor_id == actor.actor_id,
            LegacyGrant.status == "PREVIEW_ACTIVE",
            Consent.status == str(ConsentStatus.GRANTED),
        )
    ).all()
    if not rows:
        raise LegacyAccessDenied("No active recipient preview grant")
    items: dict[str, MemoryView] = {}
    for grant in rows:
        snapshot = set(grant.snapshot_memory_ids)
        for item in _memories(
            session, subject_id=subject_id, actor_id=grant.grantor_actor_id
        ):
            if (
                item.memory_item_id in snapshot
                and item.domain in grant.allowed_domains
                and item.correction is None
            ):
                items[item.memory_item_id] = item
        _audit(session, grant_id=grant.grant_id, actor_id=actor.actor_id, action="READ")
    session.commit()
    return RecipientMemories(
        subject_id=subject_id, mode="PREVIEW", items=list(items.values())
    )
