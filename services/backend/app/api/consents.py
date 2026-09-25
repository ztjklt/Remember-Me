"""The consent boundary.

Consent is granted, listed, revoked, and — separately — verified. The separation
is the point: a grant is a record that something was permitted, and verification
is the check that a specific operation, on a specific subject, for a specific
scope, is permitted right now (ADR-0001 D7).

`POST /authorize` is the boundary every sensitive operation goes through. It is a
POST because it is a question asked by an operation, not a resource being read,
and because it can fail with 403 rather than hiding the answer in a body. The
recording path (Issue #1) and the future voice pipeline both answer the same
question here; the difference between them is only the scope they name. A
RECORDING grant therefore cannot authorize a VOICE operation, and the protocol
has no way to express "either one".

URL paths and payloads here are Backend-owned. The integration contract does not
define a consent shape; it defines who an Episode is attributed to and which
consent reference accompanies a capture.

A grant is attributed as well as scoped: the granting Actor comes from the
credential, and every later read, use, and revocation of that grant is scoped
back to the same Actor. A consent belonging to another Actor is answered exactly
as one that does not exist, so no response confirms that another Actor's grant
exists. Granting is deliberately *not* restricted to a subset of Actors — in
Phase 1 a grant is the only way authority over a subject's record is acquired,
and the subject-to-actor relationship is not modeled yet, so narrowing who may
grant would leave no way to obtain the authority the rest of this file enforces
(ADR-0001 D7).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Actor, Consent, ConsentScope, as_utc
from ..repositories.consents import ConsentRepository
from ..repositories.subjects import SubjectRepository
from ..security import current_actor, require_subject_owner

router = APIRouter(prefix="/api/v1/consents", tags=["consent"])


class ConsentResponse(BaseModel):
    consent_id: str
    subject_id: str
    granted_by_actor_id: str
    scope: ConsentScope
    status: str
    granted_at: datetime
    revoked_at: datetime | None
    evidence_ref: str | None

    @classmethod
    def of(cls, consent: Consent) -> "ConsentResponse":
        return cls(
            consent_id=consent.consent_id,
            subject_id=consent.subject_id,
            granted_by_actor_id=consent.granted_by_actor_id,
            scope=ConsentScope(consent.scope),
            status=consent.status,
            granted_at=as_utc(consent.granted_at),
            revoked_at=None if consent.revoked_at is None else as_utc(consent.revoked_at),
            evidence_ref=consent.evidence_ref,
        )


class GrantConsentRequest(BaseModel):
    """A grant request.

    Unknown fields are refused rather than ignored: a client that sends
    granted_by_actor_id must be told its attribution is not accepted, not have it
    silently dropped (the contract sets the same rule for its own shapes).
    """

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    scope: ConsentScope
    evidence_ref: str | None = None


class AuthorizeRequest(BaseModel):
    """The question a sensitive operation asks before it does anything."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str
    scope: ConsentScope
    consent_id: str | None = None


class AuthorizeResponse(BaseModel):
    authorized: bool
    consent_id: str
    subject_id: str
    scope: ConsentScope
    granted_at: datetime


@router.post(
    "", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED
)
def grant_consent(
    payload: GrantConsentRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ConsentResponse:
    """Record a granted consent of one scope for one subject.

    The granting Actor is the authenticated caller, never a value from the body,
    so a grant always names who made it.
    """
    SubjectRepository(session).require(payload.subject_id)
    require_subject_owner(session, subject_id=payload.subject_id, actor_id=actor.actor_id)
    consent = ConsentRepository(session).grant(
        subject_id=payload.subject_id,
        granted_by_actor_id=actor.actor_id,
        scope=payload.scope,
        evidence_ref=payload.evidence_ref,
    )
    session.commit()
    return ConsentResponse.of(consent)


@router.post("/authorize", response_model=AuthorizeResponse)
def authorize(
    payload: AuthorizeRequest,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> AuthorizeResponse:
    """Verify that an active consent of the caller's permits this scope for this subject.

    Raises CONSENT_REQUIRED when no reference was supplied, CONSENT_NOT_FOUND when
    the reference is not the caller's own grant, and CONSENT_INVALID when it is
    the caller's but does not authorize the requested scope — including when it is
    an active grant for a different scope.
    """
    consent = ConsentRepository(session).require_active(
        payload.consent_id,
        subject_id=payload.subject_id,
        scope=payload.scope,
        actor_id=actor.actor_id,
    )
    return AuthorizeResponse(
        authorized=True,
        consent_id=consent.consent_id,
        subject_id=consent.subject_id,
        scope=ConsentScope(consent.scope),
        granted_at=as_utc(consent.granted_at),
    )


@router.get("", response_model=list[ConsentResponse])
def list_consents(
    subject_id: str = Query(...),
    scope: ConsentScope | None = Query(None),
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> list[ConsentResponse]:
    SubjectRepository(session).require(subject_id)
    consents = ConsentRepository(session).list_for_actor(
        subject_id, actor_id=actor.actor_id, scope=scope
    )
    return [ConsentResponse.of(consent) for consent in consents]


@router.get("/{consent_id}", response_model=ConsentResponse)
def read_consent(
    consent_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ConsentResponse:
    return ConsentResponse.of(
        ConsentRepository(session).require_for(consent_id, actor_id=actor.actor_id)
    )


@router.post("/{consent_id}/revoke", response_model=ConsentResponse)
def revoke_consent(
    consent_id: str,
    actor: Actor = Depends(current_actor),
    session: Session = Depends(get_session),
) -> ConsentResponse:
    """Revoke a consent the caller granted.

    Revocation is a state change rather than a deletion: the record of what was
    permitted, by whom, and when stays, because the work done under it was done.
    A consent granted by another actor is CONSENT_NOT_FOUND here, so revocation
    cannot be used to discover or disturb another actor's grants.
    """
    repository = ConsentRepository(session)
    consent = repository.revoke(
        repository.require_for(consent_id, actor_id=actor.actor_id)
    )
    if consent.scope == str(ConsentScope.CLOUD_TWIN):
        from ..person_model import rebuild_person_model
        rebuild_person_model(session, subject_id=consent.subject_id, actor_id=actor.actor_id)
    session.commit()
    return ConsentResponse.of(consent)
