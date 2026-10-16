"""Account-free recipients are scoped capabilities, never owner Actors."""
from datetime import datetime
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, utcnow


class ContactEntrustment(Base):
    __tablename__ = 'contact_entrustments'
    __table_args__ = (UniqueConstraint('subject_id', 'author_actor_id', 'idempotency_key', name='uq_contact_entrustment_request'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(64), ForeignKey('subjects.subject_id'), index=True)
    author_actor_id: Mapped[str] = mapped_column(String(64), ForeignKey('actors.actor_id'))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    recipient_label: Mapped[str] = mapped_column(String(80))
    channel: Mapped[str] = mapped_column(String(12))
    contact_cipher: Mapped[str] = mapped_column(Text)
    contact_hash: Mapped[str] = mapped_column(String(64), index=True)
    contact_mask: Mapped[str] = mapped_column(String(254))
    invite_cipher: Mapped[str] = mapped_column(Text)
    invite_hash: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON)
    source_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='active')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    notice_status: Mapped[str] = mapped_column(String(16), default='not_sent')
    notice_attempt: Mapped[str] = mapped_column(String(64), default='')
    notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReceiptChallenge(Base):
    __tablename__ = 'receipt_challenges'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey('contact_entrustments.id'), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default='sending')
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReceiptSession(Base):
    __tablename__ = 'receipt_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey('contact_entrustments.id'), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReceiptRate(Base):
    __tablename__ = 'receipt_rates'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
