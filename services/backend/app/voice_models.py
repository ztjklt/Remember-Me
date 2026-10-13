"""Voice embodiment metadata and grants, separate from story authorization."""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class SyntheticVoiceProfile(Base):
    __tablename__ = 'synthetic_voice_profiles'
    profile_id: Mapped[str] = mapped_column(String(64), ForeignKey('voice_profiles.profile_id'), primary_key=True)
    preset: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class VoiceRecipientGrant(Base):
    __tablename__ = 'voice_recipient_grants'
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), primary_key=True)
    granted_by_actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
