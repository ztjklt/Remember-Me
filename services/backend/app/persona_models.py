"""Dialogue provenance and dedicated companion audio, separate from subject facts."""
from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class PersonaAnswerContext(Base):
    __tablename__='persona_answer_contexts'
    answer_id: Mapped[str]=mapped_column(String(64),ForeignKey('twin_answers.answer_id'),primary_key=True)
    mode: Mapped[str]=mapped_column(String(16),nullable=False)
    cloud_consent_id: Mapped[str]=mapped_column(String(64),nullable=False)
    understanding_ids: Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    contribution_ids: Mapped[list]=mapped_column(JSON,nullable=False,default=list)
    prompt_version: Mapped[str]=mapped_column(String(128),nullable=False,default='')
    review_summary: Mapped[dict]=mapped_column(JSON,nullable=False,default=dict,server_default='{}')


class CompanionAudio(Base):
    __tablename__='companion_audio'
    __table_args__=(UniqueConstraint('subject_id','author_actor_id','idempotency_key',name='uq_companion_audio_request'),)
    audio_id: Mapped[str]=mapped_column(String(64),primary_key=True)
    subject_id: Mapped[str]=mapped_column(String(64),ForeignKey('subjects.subject_id'),nullable=False,index=True)
    author_actor_id: Mapped[str]=mapped_column(String(64),ForeignKey('actors.actor_id'),nullable=False)
    idempotency_key: Mapped[str]=mapped_column(String(200),nullable=False)
    request_hash: Mapped[str]=mapped_column(String(64),nullable=False)
    purpose: Mapped[str]=mapped_column(String(16),nullable=False)
    object_key: Mapped[str]=mapped_column(String(500),nullable=False)
    content_type: Mapped[str]=mapped_column(String(100),nullable=False)
    status: Mapped[str]=mapped_column(String(20),nullable=False,default='saved')
    revision: Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    raw_transcript_text: Mapped[str]=mapped_column(Text,nullable=False,default='',server_default='')
    transcript_text: Mapped[str]=mapped_column(Text,nullable=False,default='')
    reviewed_text: Mapped[str]=mapped_column(Text,nullable=False,default='')
    model_version: Mapped[str]=mapped_column(String(128),nullable=False,default='')
    error: Mapped[str]=mapped_column(String(200),nullable=False,default='')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
