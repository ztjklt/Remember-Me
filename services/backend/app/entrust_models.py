"""Account-bound scoped entrustments; voice labels never authorize access."""
from datetime import datetime
from sqlalchemy import String,Text,JSON,DateTime,ForeignKey,Integer
from sqlalchemy.orm import Mapped,mapped_column
from .models import Base,utcnow
class LegacyState(Base):
    __tablename__='legacy_states'
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.subject_id'),primary_key=True)
    steward_actor_id:Mapped[str]=mapped_column(ForeignKey('actors.actor_id'))
    status:Mapped[str]=mapped_column(String(32),default='inactive')
    verification_history:Mapped[list]=mapped_column(JSON,default=list)
    verification_ref:Mapped[str]=mapped_column(String(256),default='')
    baseline:Mapped[dict]=mapped_column(JSON,default=dict)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class Entrustment(Base):
    __tablename__='entrustments'
    plan_id:Mapped[str]=mapped_column(String(64),primary_key=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.subject_id'),index=True)
    owner_actor_id:Mapped[str]=mapped_column(ForeignKey('actors.actor_id'))
    recipient_actor_id:Mapped[str]=mapped_column(ForeignKey('actors.actor_id'),index=True)
    recipient_label:Mapped[str]=mapped_column(String(80))
    consent_id:Mapped[str]=mapped_column(ForeignKey('consents.consent_id'))
    episode_ids:Mapped[list]=mapped_column(JSON)
    voice_consent_id:Mapped[str|None]=mapped_column(ForeignKey('consents.consent_id'),nullable=True)
    secret_hash:Mapped[str]=mapped_column(String(256))
    condition:Mapped[str]=mapped_column(String(32),default='immediate')
    status:Mapped[str]=mapped_column(String(24),default='confirmed')
    revision:Mapped[int]=mapped_column(Integer,default=1)
    failures:Mapped[int]=mapped_column(Integer,default=0)
    blocked_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class EntrustUnlock(Base):
    __tablename__='entrust_unlocks'
    unlock_id:Mapped[str]=mapped_column(String(64),primary_key=True)
    plan_id:Mapped[str]=mapped_column(ForeignKey('entrustments.plan_id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('actors.actor_id'))
    token_hash:Mapped[str]=mapped_column(String(64))
    visit_id:Mapped[str|None]=mapped_column(String(64),nullable=True)
    plan_revision:Mapped[int]=mapped_column(Integer)
    source_basis:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    answer_ids:Mapped[list]=mapped_column(JSON,default=list)

class EntrustVisit(Base):
    __tablename__='entrust_visits'
    visit_id:Mapped[str]=mapped_column(String(64),primary_key=True)
    plan_id:Mapped[str]=mapped_column(ForeignKey('entrustments.plan_id'),index=True)
    actor_id:Mapped[str]=mapped_column(ForeignKey('actors.actor_id'))
    consent_ids:Mapped[dict]=mapped_column(JSON)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
