"""Evidence-scoped organization, reviewed separately from memory extraction."""
from typing import Literal,Annotated
from uuid import uuid4
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from .access import visible_episodes, is_owner, altered_story_ids
from .materials import effective_materials
from .models import NarrativeRecord, NarrativeHistory, NarrativePreference, Episode, MemoryItem, MemoryRevision, as_utc
from .errors import RequestInvalid

FACETS = {'EXPERIENCE':'经历与转折','RELATIONSHIPS':'人物与关系','IDENTITY':'身份与角色',
          'PRACTICES':'偏好、习惯与做事方法','VALUES':'价值、信念与选择理由',
          'FEELINGS':'感受与当时状态','WISHES':'愿望、计划与牵挂','EXPRESSION':'原话、表达与寄语'}
VIEW_FACETS = [('人生足迹',{'EXPERIENCE','IDENTITY','FEELINGS'}),('重要的人',{'RELATIONSHIPS'}),
               ('在意与选择',{'PRACTICES','VALUES','WISHES'}),('声音与表达',{'EXPRESSION'})]

class RecordInput(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True,json_schema_extra={'allOf':[
        {'if':{'properties':{'same_event':{'const':True}},'required':['same_event']},'then':{'properties':{'kind':{'const':'story'}}}},
        {'if':{'properties':{'kind':{'enum':['style','letter']}},'required':['kind']},'then':{'properties':{'facets':{'contains':{'const':'EXPRESSION'}}}}}]})
    kind: Literal['story','person','observation','letter','style']
    title: str = Field(min_length=1,max_length=120)
    text: str = Field(min_length=1,max_length=1500)
    evidence_ids: list[str] = Field(min_length=1,max_length=64,json_schema_extra={'uniqueItems':True})
    facets: list[Literal['EXPERIENCE','RELATIONSHIPS','IDENTITY','PRACTICES','VALUES','FEELINGS','WISHES','EXPRESSION']] = Field(min_length=1,max_length=8,json_schema_extra={'uniqueItems':True})
    time_text: str = Field(default='',max_length=200)
    place_text: str = Field(default='',max_length=200)
    aliases: list[Annotated[str,Field(min_length=1,max_length=120)]] = Field(default_factory=list,max_length=12)
    same_event: bool = False
    recipient_label: str = Field(default='',max_length=120)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.evidence_ids))!=len(self.evidence_ids) or len(set(self.facets))!=len(self.facets):
            raise ValueError('Duplicate evidence or facets')
        if any(not a.strip() or len(a)>120 for a in self.aliases): raise ValueError('Invalid alias')
        if self.same_event and self.kind!='story': raise ValueError('Only event stories group observations')
        if self.kind in {'style','letter'} and 'EXPRESSION' not in self.facets: raise ValueError('Expression facet required')
        return self

def material_map(session, subject, actor, cloud=False, episode_ids=None):
    ids=visible_episodes(session,subject,actor,cloud=cloud)
    if not is_owner(session,subject,actor): ids-=altered_story_ids(session,ids)
    if episode_ids is not None: ids &= set(episode_ids)
    return contextual_sources(session,subject,effective_materials(session,subject,ids,enforce_budget=cloud),visible_episode_ids=ids)

def contextual_sources(session,subject,candidates,*,visible_episode_ids=None):
    changes={r.target_memory_id:r for r in session.scalars(select(MemoryRevision).where(
        MemoryRevision.subject_id==subject,MemoryRevision.status=='confirmed',MemoryRevision.kind=='change'))}
    contexts={};sources={}
    for c in candidates:
        context=''
        if c['memory_item_id'] in changes:
            change=changes[c['memory_item_id']]
            context='历史记载，后来已有变化，不代表当前状态。'
            if visible_episode_ids is None or change.episode_id in visible_episode_ids:
                context+='变化时间：'+(change.time_text or '未确定')
        memory=session.get(MemoryItem,c['memory_item_id'])
        if memory and (memory.item_metadata or {}).get('relation_kind')=='change':
            context+='变化后的记载；时间：'+str(memory.item_metadata.get('time_context') or '未确定')
        for e in c['evidence']:
            sources[e['evidence_id']]=dict(e)
            contexts.setdefault(e['evidence_id'],set()).add(context)
    return {id:{**source,'temporal_context':'；'.join(sorted(t for t in contexts[id] if t))} for id,source in sources.items()}

def fingerprint(source):
    return hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def validate_payload(payload, sources):
    data=RecordInput.model_validate(payload).model_dump()
    if any(e not in sources for e in data['evidence_ids']): raise RequestInvalid('来源不可用，请重新整理。')
    excerpts=[sources[e]['excerpt'] for e in data['evidence_ids']]
    # These fields claim exact names/time/location, not generated interpretations.
    for phrase in [data['time_text'],data['place_text'],*data['aliases']]:
        if phrase and not any(phrase in text for text in excerpts): raise RequestInvalid('时间、地点和别名必须能在所选原文中找到。')
    if data['kind'] in {'letter','style'} and not any(data['text'] in t for t in excerpts):
        raise RequestInvalid('寄语和表达范例须逐字选取本人原话，不能扩写。')
    if data['kind'] in {'letter','style'} and any(sources[e]['source_type'] not in {'SUBJECT','CALIBRATION'} for e in data['evidence_ids']):
        raise RequestInvalid('他人转述不能作为本人的寄语或表达范例。')
    return data

def valid_record(row,sources):
    return bool(row.evidence_snapshot) and all(e in sources and fingerprint(sources[e])==value for e,value in row.evidence_snapshot.items())

def record_view(row,sources,owner):
    valid=valid_record(row,sources)
    return dict(id=row.id,**row.payload,status=row.status if valid or row.status=='rejected' else 'stale',
        revision=row.revision,model_version=row.model_version,prompt_version=row.prompt_version,
        created_at=as_utc(row.created_at).isoformat(),updated_at=as_utc(row.updated_at).isoformat(),
        evidence=[sources[e] for e in row.payload['evidence_ids'] if e in sources] if valid else [],
        label='本人审核的系统整理' if row.status=='confirmed' else '待核对的整理建议',
        historical=not valid,source_valid=valid)

def visible_records(session,subject,actor,*,sources=None):
    if sources is None: sources=material_map(session,subject,actor)
    owner=is_owner(session,subject,actor)
    rows=session.scalars(select(NarrativeRecord).where(NarrativeRecord.subject_id==subject).order_by(NarrativeRecord.created_at,NarrativeRecord.id))
    return [record_view(r,sources,owner) for r in rows if owner or (r.status=='confirmed' and valid_record(r,sources))]

def audit(session,row,actor,action):
    session.add(NarrativeHistory(id='nh_'+uuid4().hex[:20],record_id=row.id,actor_id=actor,
        revision=row.revision,action=action,payload={'record':row.payload,'status':row.status}))

def create_record(session,subject,actor,payload,sources,model='owner',prompt='owner'):
    data=validate_payload(payload,sources)
    row=NarrativeRecord(id='nr_'+uuid4().hex[:20],subject_id=subject,kind=data['kind'],status='pending',
        payload=data,evidence_snapshot={e:fingerprint(sources[e]) for e in data['evidence_ids']},
        revision=1,model_version=model,prompt_version=prompt)
    session.add(row);session.flush();audit(session,row,actor,'create')
    return row

def event_support(session,subject,evidence_ids,sources):
    """Only explicitly confirmed event membership establishes distinct events."""
    groups=[]
    for row in session.scalars(select(NarrativeRecord).where(NarrativeRecord.subject_id==subject,NarrativeRecord.kind=='story',NarrativeRecord.status=='confirmed')):
        if row.payload.get('same_event') and valid_record(row,sources):
            members=set(row.payload['evidence_ids'])
            intersect=[g for g in groups if g&members]
            for g in intersect: members|=g;groups.remove(g)
            groups.append(members)
    selected=set(evidence_ids)
    # Unknown assignments are not proof of additional independent events.
    selected_groups=[g for g in groups if g&selected]
    return len(selected_groups)
