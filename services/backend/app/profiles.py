"""Durable schema-worker proposals; human approval is separate from model execution."""
from uuid import uuid4
import hashlib
import json
import re
import httpx
from sqlalchemy import select
from .access import source_basis, publication_lock, require_owner, require_cloud, visible_episodes
from .models import ProfileCandidate, ProfileRefresh, Episode, utcnow
from .materials import effective_materials
from .repositories.person_model import PERSON_DOMAINS


class ProfileClient:
    def __init__(self, url, timeout=45):
        self.url, self.timeout = url.rstrip('/')+'/profile-proposals', timeout
    def propose(self, materials):
        r = httpx.post(self.url, json={'materials':materials}, timeout=self.timeout,
                      follow_redirects=False, trust_env=False)
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
    basis = source_basis(session, subject_id, include_profiles=False)
    return list(session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id==subject_id,
        ProfileCandidate.status=='confirmed', ProfileCandidate.source_basis==basis)))


def run_profile_once(database, client):
    """Claim/commit, perform network work unlocked, then source-CAS publication.

    Explicit retries create a new queued job; interrupted jobs are failed on
    worker startup, never silently resubmitted to the cloud.
    """
    with database.session() as session:
        publication_lock(session, '')
        job = session.scalar(select(ProfileRefresh).where(ProfileRefresh.status=='queued').order_by(ProfileRefresh.created_at))
        if job is None:
            session.rollback(); return None
        id, subject, actor, consent = job.job_id, job.subject_id, job.actor_id, job.consent_id
        job.status, job.updated_at = 'running', utcnow()
        session.commit()
    try:
        with database.session() as session:
            publication_lock(session,subject)
            require_owner(session,subject,actor); require_cloud(session,subject,actor,consent)
            candidates = effective_materials(session,subject,visible_episodes(session,subject,actor,cloud=True))
            materials = {e['evidence_id']:e for c in candidates for e in c['evidence']}
            # Third party evidence is useful for factual QA but never establishes
            # the narrator's psychological tendencies.
            materials = {k:v for k,v in materials.items() if v['source_type'] in {'SUBJECT','CALIBRATION'}}
            # A repeated upload/copy of one narrative is not a second observation,
            # even when the model cites different excerpts from the two copies.
            episode_texts = {eid: re.sub(r'[\W_]+','',session.get(Episode,eid).transcript or '').casefold()
                for eid in {m['episode_id'] for m in materials.values()}}
            basis = source_basis(session,subject,include_profiles=False)
            session.commit()
        result = client.propose([{k:v for k,v in m.items() if k!='source_type'} for m in materials.values()]) if materials else {
            'candidates':[], 'model_version':'no-evidence','prompt_version':'no-evidence'}
        if not isinstance(result,dict) or not isinstance(result.get('candidates'),list) or len(result['candidates'])>8:
            raise ValueError('人物候选结构无效')
        validated = []
        for item in result['candidates']:
            if set(item) != {'domain','kind','statement','context','evidence_ids','counter_evidence_ids'}:
                raise ValueError('人物候选字段无效')
            if item['domain'] not in PERSON_DOMAINS or item['kind'] not in {'trait','habit'}:
                raise ValueError('人物候选领域无效')
            if any(not isinstance(item[k],str) or not item[k].strip() or len(item[k])>1000 for k in ('statement','context')):
                raise ValueError('人物候选文字无效')
            ids, counters = item['evidence_ids'], item['counter_evidence_ids']
            if (not isinstance(ids,list) or not ids or not isinstance(counters,list) or
                any(not isinstance(i,str) for i in ids+counters) or len(set(ids))!=len(ids) or
                any(i not in materials for i in ids+counters)):
                raise ValueError('人物候选引用无效')
            texts = {re.sub(r'[\W_]+','',materials[i]['excerpt']).casefold() for i in ids}
            episodes = {episode_texts[materials[i]['episode_id']] for i in ids}
            validated.append((item,min(len(texts),len(episodes))))
        for k in ('model_version','prompt_version'):
            if not isinstance(result.get(k),str) or not result[k] or len(result[k])>128:
                raise ValueError('人物候选模型版本无效')
        with database.session() as session:
            publication_lock(session,subject)
            require_owner(session,subject,actor); require_cloud(session,subject,actor,consent)
            if basis != source_basis(session,subject,include_profiles=False):
                raise ValueError('SOURCE_CHANGED：资料或授权已变化，请明确重试')
            for item,count in validated:
                identity = hashlib.sha256(json.dumps([subject,basis,item],sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:40]
                if session.get(ProfileCandidate,'pc_'+identity) is None:
                    session.add(ProfileCandidate(candidate_id='pc_'+identity, subject_id=subject,
                        **item, independent_episodes=count, source_basis=basis, status='pending',
                        model_version=result['model_version'],prompt_version=result['prompt_version']))
            job=session.get(ProfileRefresh,id); job.status,job.updated_at='complete',utcnow()
            session.commit()
    except Exception as exc:
        with database.session() as session:
            job=session.get(ProfileRefresh,id); job.status,job.updated_at='failed',utcnow()
            # No provider body or credentials in durable user-visible errors.
            job.error = str(exc) if isinstance(exc,ValueError) else '人物归纳未完成；已保存资料保留，请检查服务后重试。'
            session.commit()
    return id
