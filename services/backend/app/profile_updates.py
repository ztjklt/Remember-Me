"""Owner-selected relations, no autonomous trait overwrites or parallel store."""
import hashlib
import json
from uuid import uuid4
from .models import ProfileCandidate
from .access import visible_episodes
from .materials import effective_materials
from .errors import AppError


class ProfileChanged(AppError):
    code='SOURCE_CHANGED'
    http_status=409


def evidence_fingerprint(evidence):
    return hashlib.sha256(json.dumps(evidence,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def valid_snapshot(session,subject,actor,row,*,require_saved=False):
    sources={e['evidence_id']:e for c in effective_materials(session,subject,visible_episodes(session,subject,actor)) for e in c['evidence']}
    ids=set(row.evidence_ids+row.counter_evidence_ids)
    if not row.evidence_ids or not ids <= sources.keys():
        raise ProfileChanged('人物理解的依据已不可用，请重新归纳。')
    current={id:evidence_fingerprint(sources[id]) for id in sorted(ids)}
    if require_saved and (not row.evidence_snapshot or row.evidence_snapshot!=current):
        raise ProfileChanged('旧理解的原始依据无法重新验证，请生成新的候选。')
    return current


def update_view(row):
    keys=('update_id','candidate_id','target_candidate_id','result_candidate_id','action','reason','time_text','base_source_version','status',
          'origin','model_version','prompt_version','suggestion_evidence_ids')
    return {key:getattr(row,key) for key in keys} | {
        'created_at':row.created_at.isoformat(),
        'question':'这两条理解是在不同时间或情境下的变化，还是其中一条不准确？' if row.action=='CONFLICT' else None}


def apply_update(session,row,candidate,target,basis,actor):
    candidate_snapshot=valid_snapshot(session,row.subject_id,actor,candidate)
    if row.action=='ADD':
        candidate.status='confirmed';candidate.evidence_snapshot=candidate_snapshot
        row.result_candidate_id=candidate.candidate_id
    elif row.action=='CONFLICT':
        candidate.status=target.status='conflicted'
        candidate.evidence_snapshot=candidate_snapshot
    else:
        # Each confirmation creates a version. Old statements and evidence IDs
        # remain unchanged; only their lifecycle state changes.
        supporting=row.action=='SUPPORT'
        support=list(dict.fromkeys((target.evidence_ids if supporting else [])+candidate.evidence_ids))
        counter=list(dict.fromkeys((target.counter_evidence_ids if supporting else [])+candidate.counter_evidence_ids))
        result=ProfileCandidate(candidate_id='pc_'+uuid4().hex,subject_id=row.subject_id,
            domain=candidate.domain,kind=candidate.kind,
            statement=target.statement if supporting else candidate.statement,
            context=target.context if supporting else candidate.context+'；本人确认的变化时间：'+row.time_text,
            evidence_ids=support,counter_evidence_ids=counter,
            # This field must not be inflated into an independent-event count.
            independent_episodes=1, source_basis=basis,status='confirmed',
            model_version=candidate.model_version,prompt_version=candidate.prompt_version)
        result.evidence_snapshot=valid_snapshot(session,row.subject_id,actor,result)
        session.add(result);session.flush()
        target.status='superseded';candidate.status='applied'
        row.result_candidate_id=result.candidate_id
