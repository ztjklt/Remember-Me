"""Same durable worker and consent/CAS rules as profile tasks; no hidden retries."""
import hashlib
import json
from sqlalchemy import select
from .access import publication_lock,require_owner,require_cloud,source_basis
from .models import ProfileRefresh,NarrativeRecord,utcnow
from .narrative import material_map,validate_payload,create_record

def run_narrative_job(database,client,id,subject,actor,consent):
    with database.session() as session:
        publication_lock(session,subject);require_owner(session,subject,actor);require_cloud(session,subject,actor,consent)
        job=session.get(ProfileRefresh,id)
        ids=(job.request_payload or {}).get('episode_ids',[])
        sources=material_map(session,subject,actor,cloud=True,episode_ids=ids or None)
        if not sources: raise ValueError('没有可整理的已核对有效材料。')
        # Cloud selection and authorization are different scopes. Only selected
        # text goes to the model; stable local fingerprints use the full owner
        # view, so an omitted private change date cannot make a new draft stale.
        canonical_sources=material_map(session,subject,actor)
        basis=source_basis(session,subject);session.commit()
    result=client.propose_narrative({'materials':list(sources.values())})
    if not isinstance(result,dict) or set(result)!={'records','model_version','prompt_version'}:
        raise ValueError('整理结果结构无效。')
    records=result['records']
    if not isinstance(records,list) or len(records)>16: raise ValueError('整理结果数量无效。')
    for key in ('model_version','prompt_version'):
        if not isinstance(result[key],str) or not 0<len(result[key])<=128: raise ValueError('整理模型信息无效。')
    records=[validate_payload(item,sources) for item in records]
    with database.session() as session:
        publication_lock(session,subject);require_owner(session,subject,actor);require_cloud(session,subject,actor,consent)
        if basis!=source_basis(session,subject): raise ValueError('资料或授权已变化，请明确重试。')
        serialize=lambda p:json.dumps(p,sort_keys=True,ensure_ascii=False)
        existing={serialize(r.payload) for r in session.scalars(select(NarrativeRecord).where(NarrativeRecord.subject_id==subject))}
        for data in records:
            if serialize(data) not in existing:
                create_record(session,subject,actor,data,canonical_sources,result['model_version'],result['prompt_version'])
                existing.add(serialize(data))
        job=session.get(ProfileRefresh,id);job.status='complete';job.updated_at=utcnow();session.commit()
