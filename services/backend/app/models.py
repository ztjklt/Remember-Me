from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Restore the UTC offset on a stored timestamp.

    SQLite has no timezone-aware datetime type, so a value written as UTC comes
    back naive while PostgreSQL returns it with the offset. Everything this
    application writes is UTC (see utcnow), so re-attaching UTC states what was
    stored rather than guessing; without it the same field would serialize with
    an offset from one backend and without one from the other (ADR-0001 D3).
    """
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class Base(DeclarativeBase):
    pass


class ConsentScope(StrEnum):
    """Consent scopes. Each is a separate grant, never a label on another grant.

    RECORDING covers capturing the subject's audio and text. VOICE covers the
    separate permission to build and use a voice profile from that audio. They are
    distinct values in the same table so that the verification rule is one query
    against one shape, and so that a recording consent can never satisfy a voice
    operation (ADR-0001 D7, Issue #9).

    A new scope is a deliberate act: it needs a value here, a migration extending
    the database constraint, and — if it crosses a module boundary — the
    Issue/proposal route CONTRIBUTING.md requires.
    """

    RECORDING = "RECORDING"
    VOICE = "VOICE"


# The database refuses a scope this codebase does not register, so a typo or a
# hand-written row cannot create a grant that no verification rule will ever
# match. Written as SQL rather than as a SQLAlchemy expression so the migration
# can state the same list.
CONSENT_SCOPE_CHECK = "scope IN ({})".format(
    ", ".join(f"'{scope.value}'" for scope in ConsentScope)
)


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    REVOKED = "revoked"


class Subject(Base):
    """The modeled person. Durable across Actor changes."""

    __tablename__ = "subjects"

    subject_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Actor(Base):
    """Whoever currently operates the app.

    May be the Subject or another person. Kept distinct from Subject from the
    start so Creator Mode and Legacy Mode can move between actors around one
    subject (Issue #8 principle note).
    """

    __tablename__ = "actors"
    __table_args__ = (Index("ix_actors_token_hash", "token_hash", unique=True),)

    actor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Only the digest of an actor token is stored. See app/security.py.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Consent(Base):
    """A granted permission record tying a Subject to the Actor who granted it.

    A sensitive operation must verify an active consent for the subject and the
    required scope. Merely recording a consent reference is not enough
    (ADR-0001 D7).
    """

    __tablename__ = "consents"
    __table_args__ = (
        Index("ix_consents_subject_scope_status", "subject_id", "scope", "status"),
        CheckConstraint(CONSENT_SCOPE_CHECK, name="ck_consents_scope"),
    )

    consent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("subjects.subject_id", ondelete="RESTRICT"), nullable=False
    )
    granted_by_actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("actors.actor_id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )