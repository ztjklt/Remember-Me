from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ConsentInvalid, ConsentNotFound, ConsentRequired
from ..models import Consent, ConsentScope, ConsentStatus, utcnow


class ConsentRepository:
    """Consent records and the verification rule that guards sensitive work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, consent: Consent) -> Consent:
        self.session.add(consent)
        return consent

    def get(self, consent_id: str) -> Consent | None:
        return self.session.get(Consent, consent_id)

    def require(self, consent_id: str) -> Consent:
        """Return the consent record or fail with CONSENT_NOT_FOUND."""
        consent = self.get(consent_id)
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

    def list_for_subject(
        self, subject_id: str, *, scope: ConsentScope | None = None
    ) -> list[Consent]:
        statement = select(Consent).where(Consent.subject_id == subject_id)
        if scope is not None:
            statement = statement.where(Consent.scope == str(scope))
        return list(self.session.scalars(statement.order_by(Consent.created_at)))

    def find_active(
        self, consent_id: str, *, subject_id: str, scope: ConsentScope
    ) -> Consent | None:
        """Return the consent only if it is granted for this subject and scope."""
        return self.session.scalars(
            select(Consent).where(
                Consent.consent_id == consent_id,
                Consent.subject_id == subject_id,
                Consent.scope == str(scope),
                Consent.status == ConsentStatus.GRANTED,
                Consent.revoked_at.is_(None),
            )
        ).one_or_none()

    def require_active(
        self, consent_id: str | None, *, subject_id: str, scope: ConsentScope
    ) -> Consent:
        """Verify a granted consent for a subject and scope, or raise.

        A missing reference is CONSENT_REQUIRED. A reference that exists but is
        revoked, belongs to another subject, or covers another scope is
        CONSENT_INVALID. Recording consent never satisfies another scope
        (ADR-0001 D7).
        """
        if not consent_id:
            raise ConsentRequired(
                f"A {scope} consent reference is required for this operation"
            )
        consent = self.find_active(consent_id, subject_id=subject_id, scope=scope)
        if consent is None:
            raise ConsentInvalid(
                f"Consent {consent_id} is not an active {scope} consent "
                f"for subject {subject_id}"
            )
        return consent

    def revoke(self, consent: Consent, *, at: datetime | None = None) -> Consent:
        consent.status = ConsentStatus.REVOKED
        consent.revoked_at = at or utcnow()
        return consent