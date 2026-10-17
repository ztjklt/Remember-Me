"""Explicit side records, never inputs to canonical facts or model learning."""
from datetime import datetime
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class ContributionGrant(Base):
    __tablename__ = 'contribution_grants'
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), primary_key=True)
    author_actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class SideRecord:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'), nullable=False, index=True)
    author_actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    last_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CompanionContribution(SideRecord, Base):
    __tablename__ = 'companion_contributions'
    __table_args__ = (
        UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_contributions_idempotency'),
        CheckConstraint("classification IN ('firsthand','reported','opinion')",name='ck_contributions_classification'),
        CheckConstraint("status IN ('pending','accepted','rejected','disagreement','withdrawn')",name='ck_contributions_status'),
    )
    classification: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_actor_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    audio_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    narrative_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model_use_author_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_use_owner_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CompanionLetter(SideRecord, Base):
    __tablename__ = 'companion_letters'
    __table_args__ = (
        UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_letters_idempotency'),
        CheckConstraint("status IN ('draft','published','revoked')",name='ck_letters_status'),
    )
    recipient_actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class LetterRecallCue(Base):
    __tablename__ = 'letter_recall_cues'
    letter_id: Mapped[str] = mapped_column(String(64), ForeignKey('companion_letters.id'), primary_key=True)
    letter_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False)


class SealedSnapshot(SideRecord, Base):
    __tablename__ = 'sealed_snapshots'
    __table_args__ = (
        UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_snapshots_idempotency'),
        CheckConstraint("status IN ('sealed','revoked')",name='ck_snapshots_status'),
    )
    recipient_actor_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
