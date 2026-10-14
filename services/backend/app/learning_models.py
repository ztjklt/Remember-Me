"""Owner-scoped training consent, candidates and sealed evaluation records."""
from datetime import datetime
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow

class LearningPreference(Base):
    __tablename__='learning_preferences'
    subject_id: Mapped[str]=mapped_column(String(64),ForeignKey('subjects.subject_id'),primary_key=True)
    actor_id: Mapped[str]=mapped_column(String(64),ForeignKey('actors.actor_id'),primary_key=True)
    enabled: Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    consent_id: Mapped[str|None]=mapped_column(String(64),ForeignKey('consents.consent_id'),nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)

class PersonalTrainingJob(Base):
    __tablename__='personal_training_jobs'
    __table_args__=(Index('ix_personal_training_owner','subject_id','actor_id','created_at'),)
    job_id: Mapped[str]=mapped_column(String(64),primary_key=True)
    subject_id: Mapped[str]=mapped_column(String(64),ForeignKey('subjects.subject_id'),nullable=False)
    actor_id: Mapped[str]=mapped_column(String(64),ForeignKey('actors.actor_id'),nullable=False)
    consent_id: Mapped[str]=mapped_column(String(64),ForeignKey('consents.consent_id'),nullable=False)
    source_basis: Mapped[str]=mapped_column(String(64),nullable=False)
    person_model_version: Mapped[int]=mapped_column(Integer,nullable=False)
    dataset_sha256: Mapped[str]=mapped_column(String(64),nullable=False)
    base_model: Mapped[str]=mapped_column(String(128),nullable=False)
    status: Mapped[str]=mapped_column(String(32),nullable=False)
    counts: Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    result: Mapped[dict|None]=mapped_column(JSON,nullable=True)
    worker_id: Mapped[str|None]=mapped_column(String(64),nullable=True)
    lease_token_hash: Mapped[str|None]=mapped_column(String(64),nullable=True)
    lease_expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)

class PersonalTrainerHeartbeat(Base):
    __tablename__='personal_trainer_heartbeats'
    worker_id: Mapped[str]=mapped_column(String(64),primary_key=True)
    base_model: Mapped[str]=mapped_column(String(128),nullable=False)
    available: Mapped[bool]=mapped_column(Boolean,nullable=False)
    seen_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)

class FidelityCase(Base):
    __tablename__='fidelity_cases'
    __table_args__=(Index('ix_fidelity_owner','subject_id','actor_id','created_at'),)
    case_id: Mapped[str]=mapped_column(String(64),primary_key=True)
    subject_id: Mapped[str]=mapped_column(String(64),ForeignKey('subjects.subject_id'),nullable=False)
    actor_id: Mapped[str]=mapped_column(String(64),ForeignKey('actors.actor_id'),nullable=False)
    question: Mapped[str]=mapped_column(Text,nullable=False)
    question_group_id: Mapped[str]=mapped_column(String(64),nullable=False)
    locked_answer: Mapped[str]=mapped_column(Text,nullable=False)
    answer_id: Mapped[str]=mapped_column(String(64),nullable=False)
    response_type: Mapped[str]=mapped_column(String(16),nullable=False)
    model_version: Mapped[str]=mapped_column(String(128),nullable=False)
    person_model_version: Mapped[int]=mapped_column(Integer,nullable=False)
    source_basis: Mapped[str]=mapped_column(String(64),nullable=False)
    exposure_manifest: Mapped[dict]=mapped_column(JSON,nullable=False)
    human_answer: Mapped[str|None]=mapped_column(Text,nullable=True)
    ratings: Mapped[dict|None]=mapped_column(JSON,nullable=True)
    human_confirmed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    rated_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
