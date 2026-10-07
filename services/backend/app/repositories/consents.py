from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ConsentInvalid, ConsentNotFound, ConsentRequired
from ..models import Consent, ConsentScope, ConsentStatus, utcnow


class ConsentRepository:
    """Consent records and the verification rule that guards sensitive work.

    Every method that answers a request is scoped to the actor making it: a grant
    belongs to the actor that made it and to nobody else. A consent belonging to
    another actor is reported exactly as one that does not exist, so no response
    discloses that another actor's grant exists (ADR-0001 D7).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, consent: Consent) -> Consent:
        self.session.add(consent)
        return consent

    def for_actor(self, consent_id: str, *, actor_id: str) -> Consent | None:
        """The consent as this actor may see it, or None when it is not theirs."""
        return self.session.scalars(
            select(Consent).where(
                Consent.consent_id == consent_id,
                Consent.granted_by_actor_id == actor_id,
            )
        ).one_or_none()

    def require_for(self, consent_id: str, *, actor_id: str) -> Consent:
        """Return the caller's own consent record, or fail CONSENT_NOT_FOUND.

        The scoping is the authorization rule rather than a convenience: there is
        deliberately no unscoped lookup for a request handler to reach for.
        """
        consent = self.for_actor(consent_id, actor_id=actor_id)
        if consent is None:
            raise ConsentNotFound(f"No consent with id {consent_id}")
        return consent

    def grant(
        self,
        *,
        subject_id: str,
        granted_by_actor_id: str,
        scope: ConsentScope,
        evidence_ref: str | None = None,
    ) -> Consent:
        """Record a granted consent for one scope.

        Recording the grant and verifying it are deliberately separate: this
        method asserts nothing about the operation that will later rely on it.
        """
        consent = Consent(
            consent_id=f"consent_{uuid4().hex[:16]}",
            subject_id=subject_id,
            granted_by_actor_id=granted_by_actor_id,
            scope=str(scope),
            status=str(ConsentStatus.GRANTED),
            granted_at=utcnow(),
            evidence_ref=evidence_ref,
        )
        self.session.add(consent)
        return consent

    def list_for_actor(
        self,
        subject_id: str,
        *,
        actor_id: str,
        scope: ConsentScope | None = None,
    ) -> list[Consent]:
        """The consents this actor granted for this subject, and only those.

        Listing is filtered rather than refused: another actor's grants for the
        same subject are not an error to report, they are simply not this
        caller's business.
        """
        statement = select(Consent).where(
            Consent.subject_id == subject_id,
            Consent.granted_by_actor_id == actor_id,
        )
        if scope is not None:
            statement = statement.where(Consent.scope == str(scope))
        return list(self.session.scalars(statement.order_by(Consent.created_at)))

    def require_active(
        self,
        consent_id: str | None,
        *,
        subject_id: str,
        scope: ConsentScope,
        actor_id: str,
    ) -> Consent:
        """Verify the caller's own granted consent for a subject and scope, or raise.

        A missing reference is CONSENT_REQUIRED. A reference the caller did not
        grant is CONSENT_NOT_FOUND, whether or not it exists for someone else. A
        reference the caller did grant, but which is revoked, covers another
        scope, or names another subject, is CONSENT_INVALID. Recording consent
        never satisfies another scope (ADR-0001 D7).
        """
        if not consent_id:
            raise ConsentRequired(
                f"A {scope} consent reference is required for this operation"
            )
        consent = self.require_for(consent_id, actor_id=actor_id)
        if (
            consent.subject_id != subject_id
            or consent.scope != str(scope)
            or consent.status != ConsentStatus.GRANTED
            or consent.revoked_at is not None
        ):
            raise ConsentInvalid(
                f"Consent {consent_id} is not an active {scope} consent "
                f"for subject {subject_id}"
            )
        from ..access import require_owner
        require_owner(self.session, subject_id, actor_id)
        return consent

    def revoke(self, consent: Consent, *, at: datetime | None = None) -> Consent:
        consent.status = ConsentStatus.REVOKED
        consent.revoked_at = at or utcnow()
        return consent
