"""Private, subject-scoped acoustic references. Never an access credential."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow

class VoiceIdentity(Base):
    __tablename__ = 'voice_identities'
    __table_args__ = (UniqueConstraint('subject_id','person_key',name='uq_voice_identity_person'),)
    identity_id: Mapped[str] = mapped_column(String(64),primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.subject_id'),index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('actors.actor_id'))
    person_key: Mapped[str] = mapped_column(String(128))
    label: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(24))
    consent_id: Mapped[str] = mapped_column(ForeignKey('consents.consent_id'))
    encoder_version: Mapped[str] = mapped_column(String(128))
    vectors: Mapped[list] = mapped_column(JSON)
    sources: Mapped[list] = mapped_column(JSON)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)

class VoiceUtterance(Base):
    __tablename__='voice_utterances'
    __table_args__=(UniqueConstraint('call_id','turn_id',name='uq_voice_utterance_turn'),)
    utterance_id: Mapped[str] = mapped_column(String(64),primary_key=True)
    call_id: Mapped[str] = mapped_column(ForeignKey('voice_calls.call_id'),index=True)
    turn_id: Mapped[str] = mapped_column(String(64))
    audio_key: Mapped[str] = mapped_column(String(256))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24),default='uploaded')
    report: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64),nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow)
