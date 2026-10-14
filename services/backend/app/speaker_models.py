"""Owner-scoped group recordings; never implicit Person/Voice training data."""
from datetime import datetime
from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime
from .models import Base, utcnow

class SpeakerRecording(Base):
    __tablename__ = 'speaker_recordings'
    __table_args__ = (UniqueConstraint('subject_id', 'actor_id', 'idempotency_key', name='uq_speaker_recording_request'),
                     Index('ix_speaker_recording_owner', 'subject_id', 'actor_id', 'created_at'))
    recording_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.subject_id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('actors.actor_id'))
    consent_id: Mapped[str] = mapped_column(ForeignKey('consents.consent_id'))
    policy: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    audio_key: Mapped[str] = mapped_column(String(256))
    checksum: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(64))
    speaker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(24), default='uploaded')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
