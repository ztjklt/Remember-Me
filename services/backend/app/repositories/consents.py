from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ConsentInvalid, ConsentRequired
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