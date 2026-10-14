"""Transparent source coverage; not personality fidelity or a probability."""
import hashlib
from sqlalchemy import select
from .models import PersonTrait,MemoryItem,Episode,Evidence,ModelRevision,PERSON_DOMAINS
from .voiceprints import require_verified_episode
from .errors import AppError
VERSION='seven-domains-five-sources-v1'
TARGET=5
CAP=95

def coverage(session,subject):
    groups={d:set() for d in PERSON_DOMAINS};sources={d:set() for d in PERSON_DOMAINS}
    traits=session.scalars(select(PersonTrait).where(PersonTrait.subject_id==subject,PersonTrait.status=='active'))
    for trait in traits:
        if trait.domain not in groups or not trait.evidence_ids:continue
        fingerprints=[];episode_ids=[];valid=True
        for eid in trait.evidence_ids:
            evidence=session.get(Evidence,eid)
            ep=session.get(Episode,evidence.episode_id) if evidence else None
            if not evidence or not ep or ep.subject_id!=subject or ep.status!='ready' or evidence.source_type not in ('SUBJECT','CALIBRATION') or not evidence.excerpt.strip():valid=False;break
            if (ep.capture_metadata or {}).get('origin')=='natural_dialogue':
                try:require_verified_episode(session,ep)
                except AppError:valid=False;break
            rows=list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id==ep.episode_id,MemoryItem.deleted_at.is_(None),MemoryItem.review_state=='active')))
            if not any(eid in m.evidence_ids for m in rows):valid=False;break
            # Re-uploading or cutting the same text into several clips must not
            # inflate the meter. Canonical whole source text deduplicates copies.
            text=''.join((ep.transcript or evidence.excerpt).split()).strip('。！!，,')
            fingerprints.append(hashlib.sha256(text.encode()).hexdigest());episode_ids.append(ep.episode_id)
        if valid:
            groups[trait.domain].update(fingerprints);sources[trait.domain].update(episode_ids)
    revision=session.get(ModelRevision,subject)
    units=sum(min(TARGET,len(g)) for g in groups.values())
    return {'subject_id':subject,'model_version':revision.version if revision else 0,'metric_version':VERSION,'metric':'evidence_source_coverage','percentage':units*CAP//(len(PERSON_DOMAINS)*TARGET),'cap_percentage':CAP,'covered_units':units,'target_units':len(PERSON_DOMAINS)*TARGET,'domains':[{'domain':d,'source_count':len(groups[d]),'target_sources':TARGET,'percentage':min(TARGET,len(groups[d]))*CAP//TARGET,'episode_ids':sorted(sources[d])} for d in PERSON_DOMAINS], 'explanation':'七个领域各以5个不同有效本人资料来源为当前整理目标，上限95%。重复文字、待核对资料和未解决冲突不增加覆盖；删除或撤权会重算。这不是人格复刻准确率。'}
