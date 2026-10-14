"""Separately consented provider profiles and bounded voice-call audit records."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class RealtimeVoiceProfile(Base):
    __tablename__ = 'realtime_voice_profiles'
    profile_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'))
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'))
    consent_id: Mapped[str] = mapped_column(String(64), ForeignKey('consents.consent_id'))
    sample_key: Mapped[str] = mapped_column(String(1024))
    accepted_policy: Mapped[str] = mapped_column(String(128))
    reference_text: Mapped[str] = mapped_column(Text)
    provider_voice_id: Mapped[str] = mapped_column(String(256), default='')
    model: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default='enrolling')
    fetch_digest: Mapped[str] = mapped_column(String(64), default='')
    fetch_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceCall(Base):
    __tablename__ = 'voice_calls'
    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'))
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'))
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey('realtime_voice_profiles.profile_id'))
    cloud_consent_id: Mapped[str] = mapped_column(String(64), ForeignKey('consents.consent_id'))
    voice_consent_id: Mapped[str] = mapped_column(String(64), ForeignKey('consents.consent_id'))
    recording_consent_id: Mapped[str | None] = mapped_column(ForeignKey('consents.consent_id'), nullable=True)
    speaker_consent_id: Mapped[str | None] = mapped_column(ForeignKey('consents.consent_id'), nullable=True)
    enroll_owner_voice: Mapped[bool] = mapped_column(Boolean,default=False)
    previous_answer_id: Mapped[str] = mapped_column(String(64), default='')
    completed_turn_id: Mapped[str] = mapped_column(String(64),default='')
    active_turn: Mapped[str] = mapped_column(String(64), default='')
    active_answer_id: Mapped[str] = mapped_column(String(64), default='')
    credential_digest: Mapped[str] = mapped_column(String(64))
    policy: Mapped[str] = mapped_column(String(128))
    room: Mapped[str] = mapped_column(String(128), unique=True)
    participant: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
