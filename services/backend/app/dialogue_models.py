"""Microphone utterances collected through an explicitly started owner call."""
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .models import Base, utcnow
class DialogueSample(Base):
    __tablename__='dialogue_samples'
    __table_args__=(UniqueConstraint('call_id','turn_id',name='uq_dialogue_sample_turn'),)
    sample_id:Mapped[str]=mapped_column(String(64),primary_key=True)
    call_id:Mapped[str]=mapped_column(ForeignKey('voice_calls.call_id'),index=True)
    turn_id:Mapped[str]=mapped_column(String(64))
    audio_key:Mapped[str]=mapped_column(String(256))
    checksum:Mapped[str]=mapped_column(String(64))
    duration_ms:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(24),default='uploaded')
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    lease_token:Mapped[str|None]=mapped_column(String(64),nullable=True)
    lease_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    profile_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
