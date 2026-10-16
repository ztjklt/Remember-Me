"""Durable schema-worker proposals; human approval is separate from model execution."""
from uuid import uuid4
import hashlib
import json
import re
import httpx
from sqlalchemy import select
from .access import source_basis, profile_source_basis, publication_lock, require_owner, require_cloud, visible_episodes
from .models import ProfileCandidate, ProfileRefresh, Episode, utcnow
from .materials import effective_materials
from .repositories.person_model import PERSON_DOMAINS
from .profile_batches import plan_profile_batches


class ProfileClient:
    def __init__(self, url, timeout=45):
        self.url, self.timeout = url.rstrip('/')+'/profile-proposals', timeout
    def propose(self, materials):
        r = httpx.post(self.url, json={'materials':materials}, timeout=self.timeout,
                      follow_redirects=False, trust_env=False)
        r.raise_for_status()
        return r.json()
    def propose_relations(self, payload):
        r=httpx.post(self.url.removesuffix('/profile-proposals')+'/profile-relations',json=payload,
            timeout=self.timeout,follow_redirects=False,trust_env=False)
        r.raise_for_status()
        return r.json()

    def propose_narrative(self, payload):
        r=httpx.post(self.url.removesuffix('/profile-proposals')+'/narrative-proposals',json=payload,
            timeout=self.timeout,follow_redirects=False,trust_env=False)
        r.raise_for_status()
        return r.json()


def candidate_view(row, basis):
    return {key:getattr(row,key) for key in ('candidate_id','domain','kind','statement','context',
        'evidence_ids','counter_evidence_ids','independent_episodes','model_version','prompt_version')} | {
        'status': row.status if row.source_basis == basis or row.status in {'superseded','applied','conflicted','rejected'} else 'stale',
        'stored_status':row.status,
        'source_version': row.source_basis, 'scope':'owner',
        'label': '情境化观察' if row.independent_episodes < 2 else '多次材料支持的候选',
        'created_at':row.created_at.isoformat()}


def approved_traits(session, subject_id):
    basis = profile_source_basis(session, subject_id)
    return list(session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id==subject_id,
        ProfileCandidate.status=='confirmed', ProfileCandidate.source_basis==basis)))


def validate_proposals(result, materials, episode_texts):
    if not isinstance(result,dict) or not isinstance(result.get('candidates'),list) or len(result['candidates'])>8:
        raise ValueError('人物候选结构无效')
    for k in ('model_version','prompt_version'):
        if not isinstance(result.get(k),str) or not result[k] or len(result[k])>128:
            raise ValueError('人物候选模型版本无效')
    validated = []
    for item in result['candidates']:
        if not isinstance(item,dict) or set(item) != {'domain','kind','statement','context','evidence_ids','counter_evidence_ids'}:
            raise ValueError('人物候选字段无效')
        if item['domain'] not in PERSON_DOMAINS or item['kind'] not in {'trait','habit'}:
            raise ValueError('人物候选领域无效')
        if any(not isinstance(item[k],str) or not item[k].strip() or len(item[k])>1000 for k in ('statement','context')):
            raise ValueError('人物候选文字无效')
        ids, counters = item['evidence_ids'], item['counter_evidence_ids']
        if (not isinstance(ids,list) or not ids or not isinstance(counters,list) or
            any(not isinstance(i,str) for i in ids+counters) or len(set(ids))!=len(ids) or
            len(set(counters))!=len(counters) or set(ids)&set(counters) or
            any(i not in materials for i in ids+counters)):
            raise ValueError('人物候选引用无效')
        texts = {re.sub(r'[\W_]+','',materials[i]['excerpt']).casefold() for i in ids}
        episodes = {episode_texts[materials[i]['episode_id']] for i in ids}
        validated.append((item,min(len(texts),len(episodes)),result['model_version'],result['prompt_version']))
    return validated


def run_profile_once(database, client):
    """Claim/commit, perform network work unlocked, then source-CAS publication.

    Manual jobs require explicit retry. The automatic capture workflow opts in
    to at most two retries for interruption, transport or changed sources.
    """
    with database.session() as session:
        queued=select(ProfileRefresh).where(ProfileRefresh.status=='queued').order_by(ProfileRefresh.created_at)
        if session.bind.dialect.name=='postgresql':
            # Claim only a queue row. Idle polling must not lock every source
            # table or deadlock with ordinary episode/worker writes.
            job=session.scalar(queued.with_for_update(skip_locked=True).limit(1))
        else:
            publication_lock(session, '')
            job=session.scalar(queued.limit(1))
        if job is None:
            session.rollback(); return None
        id, subject, actor, consent, kind = job.job_id, job.subject_id, job.actor_id, job.consent_id, job.kind
        job.status, job.updated_at = 'running', utcnow()
        session.commit()
    try:
        if kind=='narrative':
            from .narrative_worker import run_narrative_job
            run_narrative_job(database,client,id,subject,actor,consent)
            return id
        if kind=='relations':
            from .profile_relations import run_relations_job
            run_relations_job(database,client,id,subject,actor,consent)
            return id
        with database.session() as session:
            publication_lock(session,subject)
            require_owner(session,subject,actor); require_cloud(session,subject,actor,consent)
            # Same evidence/authorization resolver; only the aggregate budget is
            # replaced by whole-recording batches with preflight limits.
            candidates = effective_materials(session,subject,visible_episodes(session,subject,actor,cloud=True),enforce_budget=False)
            materials = {e['evidence_id']:e for c in candidates for e in c['evidence']}
            # Third party evidence is useful for factual QA but never establishes
            # the narrator's psychological tendencies.
            materials = {k:v for k,v in materials.items() if v['source_type'] in {'SUBJECT','CALIBRATION'}}
            # A repeated upload/copy of one narrative is not a second observation,
            # even when the model cites different excerpts from the two copies.
            episode_texts = {eid: re.sub(r'[\W_]+','',session.get(Episode,eid).transcript or '').casefold()
                for eid in {m['episode_id'] for m in materials.values()}}
            basis = profile_source_basis(session,subject)
            publication_basis = source_basis(session,subject)
            session.commit()
        batches = plan_profile_batches(list(materials.values()))
        validated = []
        for batch in batches:
            # Stop remaining calls if an earlier call raced a source/auth edit.
            # No database transaction is kept open during provider work.
            with database.session() as session:
                publication_lock(session,subject)
                require_owner(session,subject,actor); require_cloud(session,subject,actor,consent)
                if publication_basis != source_basis(session,subject):
                    raise ValueError('SOURCE_CHANGED：资料或授权已变化，请明确重试')
                session.commit()
            result = client.propose([{k:v for k,v in m.items() if k!='source_type'} for m in batch])
            validated.extend(validate_proposals(result,{m['evidence_id']:m for m in batch},episode_texts))
        with database.session() as session:
            publication_lock(session,subject)
            require_owner(session,subject,actor); require_cloud(session,subject,actor,consent)
            if publication_basis != source_basis(session,subject):
                raise ValueError('SOURCE_CHANGED：资料或授权已变化，请明确重试')
            for item,count,model_version,prompt_version in validated:
                identity = hashlib.sha256(json.dumps([subject,basis,item],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:40]
                if session.get(ProfileCandidate,'pc_'+identity) is None:
                    session.add(ProfileCandidate(candidate_id='pc_'+identity, subject_id=subject,
                        **item, independent_episodes=count, source_basis=basis, status='pending',
                        model_version=model_version,prompt_version=prompt_version))
            job=session.get(ProfileRefresh,id); job.status,job.updated_at='complete',utcnow()
            session.commit()
    except Exception as exc:
        with database.session() as session:
            job=session.get(ProfileRefresh,id); job.status,job.updated_at='failed',utcnow()
            # No provider body or credentials in durable user-visible errors.
            job.error = str(exc) if isinstance(exc,ValueError) else '人物归纳未完成；已保存资料保留，请检查服务后重试。'
            from .automatic_profiles import automatic_retry
            automatic_retry(job, exc)
            session.commit()
    return id
