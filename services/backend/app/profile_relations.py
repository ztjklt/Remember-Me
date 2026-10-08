"""Bounded relation worker; publishes suggestions, never current facts."""
import re
from uuid import uuid4
from sqlalchemy import select
from .access import publication_lock, require_owner, require_cloud, source_basis, visible_episodes
from .materials import effective_materials
from .models import ProfileCandidate, ProfileRefresh, ProfileUpdate, utcnow
from .profile_updates import valid_snapshot


def run_relations_job(database,client,job_id,subject,actor,consent):
    with database.session() as session:
        publication_lock(session,subject)
        require_owner(session,subject,actor);require_cloud(session,subject,actor,consent)
        sources={e['evidence_id']:e for c in effective_materials(session,subject,
            visible_episodes(session,subject,actor,cloud=True)) for e in c['evidence']
            if e['source_type'] in {'SUBJECT','CALIBRATION'}}
        basis=source_basis(session,subject,include_profiles=False)
        rows=list(session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id==subject,
            ProfileCandidate.status.in_(['pending','confirmed'])).order_by(ProfileCandidate.created_at)))
        candidates=[];targets=[]
        for row in rows:
            if row.status=='pending' and row.source_basis!=basis: continue
            if not set(row.evidence_ids+row.counter_evidence_ids)<=sources.keys(): continue
            # Confirmed-but-stale targets require exact saved evidence. An unrelated
            # new episode can advance the global basis without changing this target.
            from .profile_updates import ProfileChanged
            try: valid_snapshot(session,subject,actor,row,require_saved=row.status=='confirmed' and row.source_basis!=basis)
            except ProfileChanged: continue
            view={k:getattr(row,k) for k in ('candidate_id','domain','kind','statement','context','evidence_ids','counter_evidence_ids')}
            (candidates if row.status=='pending' else targets).append(view)
        if len(candidates)>32 or len(targets)>32:
            raise ValueError('人物候选过多，请先审核已有候选；没有截断资料。')
        used={e for row in candidates+targets for e in row['evidence_ids']+row['counter_evidence_ids']}
        materials=[{k:sources[id][k] for k in ('evidence_id','episode_id','excerpt')} for id in sorted(used)]
        if len(materials)>256 or sum(len(m['excerpt']) for m in materials)>24000:
            raise ValueError('关系建议资料超过预算，请先审核；没有截断资料。')
        full_basis=source_basis(session,subject)
        session.commit()
    result=client.propose_relations({'materials':materials,'candidates':candidates,'targets':targets}) if candidates else {
        'relations':[],'model_version':'no-evidence','prompt_version':'profile-relations-v1'}
    if not isinstance(result,dict) or set(result)!={'relations','model_version','prompt_version'}:
        raise ValueError('关系建议结构无效')
    if any(not isinstance(result[k],str) or not result[k] or len(result[k])>128 for k in ('model_version','prompt_version')):
        raise ValueError('关系建议模型版本无效')
    if not isinstance(result['relations'],list) or len(result['relations'])>16:
        raise ValueError('关系建议数量无效')
    new_by_id={c['candidate_id']:c for c in candidates};old_by_id={c['candidate_id']:c for c in targets}
    seen=set()
    for r in result['relations']:
        if not isinstance(r,dict) or set(r)!={'candidate_id','target_candidate_id','action','reason','time_text','time_evidence_id','evidence_ids'}:
            raise ValueError('关系建议字段无效')
        if any(not isinstance(r[k],str) for k in ('candidate_id','action','reason','time_text')) or not isinstance(r['evidence_ids'],list) or any(not isinstance(i,str) for i in r['evidence_ids']):
            raise ValueError('关系建议字段类型无效')
        if r['target_candidate_id'] is not None and not isinstance(r['target_candidate_id'],str): raise ValueError('目标无效')
        new=new_by_id.get(r['candidate_id']);old=old_by_id.get(r['target_candidate_id'])
        action=r['action'];ids=set(r['evidence_ids'])
        if new is None or r['candidate_id'] in seen or action not in {'ADD','SUPPORT','CONFLICT','CHANGE'}:
            raise ValueError('关系建议候选无效')
        seen.add(r['candidate_id'])
        if (action=='ADD')!=(r['target_candidate_id'] is None) or (action!='ADD' and old is None): raise ValueError('关系建议目标无效')
        if old and (new['domain'],new['kind'])!=(old['domain'],old['kind']): raise ValueError('关系建议领域不同')
        allowed=set(new['evidence_ids']+new['counter_evidence_ids']+(old['evidence_ids']+old['counter_evidence_ids'] if old else []))
        if not ids<=allowed or not ids.intersection(new['evidence_ids']) or (old and not ids.intersection(old['evidence_ids'])):
            raise ValueError('关系建议双方依据不完整')
        if not r['reason'].strip() or len(r['reason'])>1000 or len(r['time_text'])>200: raise ValueError('关系建议说明无效')
        if action=='CHANGE':
            if not isinstance(r['time_evidence_id'],str) or r['time_evidence_id'] not in ids or not r['time_text'] or r['time_text'] not in sources[r['time_evidence_id']]['excerpt']:
                raise ValueError('关系建议时间没有原文依据')
        elif r['time_text'] or r['time_evidence_id'] is not None: raise ValueError('非变化建议不能填写时间')
        if action=='SUPPORT':
            normalize=lambda text:re.sub(r'[\W_]+','',text).casefold()
            before={normalize(sources[i]['excerpt']) for i in old['evidence_ids']}
            after={normalize(sources[i]['excerpt']) for i in new['evidence_ids']}
            if not after-before: raise ValueError('重复原文不能作为新增支持')
    with database.session() as session:
        publication_lock(session,subject)
        require_owner(session,subject,actor);require_cloud(session,subject,actor,consent)
        if full_basis!=source_basis(session,subject): raise ValueError('SOURCE_CHANGED：资料或人物理解已变化，请重试')
        for r in result['relations']:
            duplicate=session.scalar(select(ProfileUpdate).where(ProfileUpdate.subject_id==subject,
                ProfileUpdate.candidate_id==r['candidate_id'],ProfileUpdate.target_candidate_id==r['target_candidate_id'],
                ProfileUpdate.action==r['action'],ProfileUpdate.base_source_version==full_basis,
                ProfileUpdate.origin=='model'))
            if duplicate is None:
                session.add(ProfileUpdate(update_id='pu_'+uuid4().hex,subject_id=subject,actor_id=actor,
                    **{k:r[k] for k in ('candidate_id','target_candidate_id','action','reason','time_text')},
                    origin='model',model_version=result['model_version'],prompt_version=result['prompt_version'],
                    suggestion_evidence_ids=r['evidence_ids'],base_source_version=full_basis,status='pending'))
        job=session.get(ProfileRefresh,job_id);job.status='complete';job.updated_at=utcnow()
        session.commit()
