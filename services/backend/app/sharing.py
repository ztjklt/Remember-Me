"""Full-recording sharing and atomic grants, reused by both sharing routes."""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select
from .access import require_owner, altered_story_ids, Hidden
from .errors import RequestInvalid, AppError
from .models import Episode, MemoryItem, Evidence, MemoryRevision, NarrativeRecord, Actor, StoryGrant, as_utc


class SharingChanged(AppError):
    code='SOURCE_CHANGED'
    http_status=409


def eligible(session,subject,actor,ids):
    require_owner(session,subject,actor)
    episodes=list(session.scalars(select(Episode).where(Episode.episode_id.in_(ids)).order_by(Episode.episode_id)))
    if len(episodes)!=len(set(ids)) or any(e.subject_id!=subject for e in episodes):
        raise Hidden('录音不存在。')
    if any(e.status!='ready' or e.transcript_reviewed_at is None for e in episodes):
        raise RequestInvalid('请先核对文字并完成整理。')
    if altered_story_ids(session,set(ids)):
        raise RequestInvalid('请先处理这些录音的修订；失效的原音不能重新分享。')
    return episodes


def preview(session,subject,actor,selection):
    require_owner(session,subject,actor)
    ids=set(selection.get('episode_ids',[])); story_rows=[]
    if selection.get('story_ids'):
        from .narrative import material_map, valid_record
        sources=material_map(session,subject,actor)
        for id in selection['story_ids']:
            row=session.get(NarrativeRecord,id)
            if row is None or row.subject_id!=subject or row.kind not in {'story','letter'}:
                raise Hidden('故事不存在。')
            if row.status!='confirmed' or not valid_record(row,sources):
                raise SharingChanged('故事已变化，请重新核对后分享。')
            story_rows.append({'id':id,'revision':row.revision,'payload':row.payload,'snapshot':row.evidence_snapshot})
            ids.update(sources[e]['episode_id'] for e in row.payload['evidence_ids'])
    if not ids or len(ids)>30:
        raise RequestInvalid('请选择1至30段完整录音。')
    episodes=eligible(session,subject,actor,ids)
    memories=list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id.in_(ids)).order_by(MemoryItem.memory_item_id)))
    def columns(rows):
        return [{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in rows]
    parts=[columns(episodes),columns(memories),story_rows]
    for model in (Evidence,MemoryRevision):
        parts.append(sorted(columns(session.scalars(select(model).where(model.episode_id.in_(ids)))),key=lambda r:json.dumps(r,sort_keys=True,default=str)))
    version=hashlib.sha256(json.dumps(parts,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
    return {'source_version':version,'episode_ids':sorted(ids),'includes_full_audio':True,
        'notice':'亲友获准后可以听完整原音、阅读完整核对文字及书面补充；不只开放摘要。',
        'items':[{'episode_id':e.episode_id,'recorded_at':as_utc(e.recorded_at).isoformat(),
            'duration_ms':e.duration_ms,'transcript':e.transcript,
            'supplement':(e.capture_metadata or {}).get('review_supplement',''),
            'memories':[m.content for m in memories if m.episode_id==e.episode_id and not m.deleted_at and m.review_state=='active']}
            for e in episodes]}


def grant_batch(session,subject,actor,reader,ids,cloud):
    eligible(session,subject,actor,ids)
    if reader==actor or session.get(Actor,reader) is None:
        raise RequestInvalid('请选择另一个有效账号。')
    # Check the entire batch before any write. Caller holds publication lock.
    previous={g.episode_id:g for g in session.scalars(select(StoryGrant).where(
        StoryGrant.episode_id.in_(ids),StoryGrant.reader_actor_id==reader,StoryGrant.revoked_at.is_(None)))}
    if any(bool(g.cloud_processing_allowed)!=cloud for g in previous.values()):
        raise RequestInvalid('变更云端使用范围前，请先撤销旧授权。')
    grants=[];created=[]
    for id in sorted(set(ids)):
        row=previous.get(id)
        if row is None:
            row=StoryGrant(grant_id='grant_'+uuid4().hex[:16],episode_id=id,reader_actor_id=reader,cloud_processing_allowed=int(cloud))
            session.add(row);created.append(row.grant_id)
        grants.append(row)
    session.flush()
    return grants,created
