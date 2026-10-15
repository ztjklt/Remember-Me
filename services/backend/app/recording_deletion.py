"""Owner-requested source erasure; keep only an inaccessible idempotency tombstone."""
from sqlalchemy import select, update, or_
from .models import (Episode, Job, MemoryItem, MemoryAudit, MemoryEmbedding, Evidence,
                     StoryGrant, MemoryRevision, CalibrationRun, ProfileCandidate, utcnow)
from .access import publication_lock, require_owner, Hidden
from .repositories.person_model import PersonModelRepository
from .retrieval import invalidate_answers


def delete_recording(session, store, subject_id, episode_id, actor_id):
    publication_lock(session, subject_id)
    require_owner(session, subject_id, actor_id)
    row = session.get(Episode, episode_id)
    if row is None or row.subject_id != subject_id:
        raise Hidden('录音不存在。')
    # Natural-dialogue deletion also retires its per-turn capture / voice samples.
    if (row.capture_metadata or {}).get('origin') == 'natural_dialogue':
        raise Hidden('请使用对话资料的删除入口。')
    metadata = row.capture_metadata or {}
    key = row.audio_object_key or metadata.get('cleanup_object_key')
    # Cancelling the lease makes an in-flight worker's final CAS roll back all
    # stage writes. The publication lock serializes this with completed writes.
    session.execute(update(Job).where(Job.episode_id == episode_id).values(
        state='failed', lease_owner=None, lease_expires_at=None,
        last_error_code='SOURCE_DELETED'))
    memories = list(session.scalars(select(MemoryItem).where(MemoryItem.episode_id == episode_id)))
    mids = [m.memory_item_id for m in memories]
    evidence = list(session.scalars(select(Evidence).where(Evidence.episode_id == episode_id)))
    eids = {e.evidence_id for e in evidence}
    for memory in memories:
        memory.deleted_at = utcnow(); memory.review_state = 'superseded'
        memory.content = ''; memory.item_metadata = {}
        embedding = session.get(MemoryEmbedding, memory.memory_item_id)
        if embedding: session.delete(embedding)
    for audit in session.scalars(select(MemoryAudit).where(MemoryAudit.memory_item_id.in_(mids))):
        audit.previous_content = ''; audit.new_content = None
    for source in evidence:
        source.excerpt = ''; source.source_ref = 'deleted:' + episode_id
    for grant in session.scalars(select(StoryGrant).where(StoryGrant.episode_id == episode_id)):
        grant.revoked_at = utcnow()
    for revision in session.scalars(select(MemoryRevision).where(or_(
            MemoryRevision.episode_id == episode_id, MemoryRevision.target_memory_id.in_(mids)))):
        revision.status = 'rejected'; revision.time_text = None
    for candidate in session.scalars(select(ProfileCandidate).where(ProfileCandidate.subject_id == subject_id)):
        if eids.intersection(candidate.evidence_ids + candidate.counter_evidence_ids):
            candidate.status = 'stale'; candidate.statement = ''; candidate.context = ''; candidate.evidence_snapshot = None
    for run in session.scalars(select(CalibrationRun).where(CalibrationRun.subject_id == subject_id)):
        if run.human_episode_id == episode_id or eids.intersection(run.locked_evidence_ids):
            run.status = 'stale'; run.summary = None; run.dimension_diffs = []
            run.source_snapshot = []; run.suggested_question = None
    row.audio_object_key = None; row.audio_ref = None; row.audio_checksum = None; row.audio_size_bytes = 0
    row.transcript = None; row.stt_transcript = None; row.model_proposals = None
    row.status = 'failed'; row.error_code = 'SOURCE_DELETED'; row.error_message = None
    row.capture_metadata = {'deleted_at': metadata.get('deleted_at') or utcnow().isoformat(),
                            **({'cleanup_object_key': key} if key else {})}
    PersonModelRepository(session).rebuild(subject_id)
    invalidate_answers(session, store, subject_id)
    session.commit()
    # Access is closed before external cleanup; retries retain the private key.
    if key:
        try: store.delete(key)
        except Exception:
            row.error_code = 'SOURCE_DELETE_PENDING'
            session.commit()
            return {'deleted': True, 'cleanup_pending': True}
        row.capture_metadata = {'deleted_at': row.capture_metadata['deleted_at']}
        session.commit()
    return {'deleted': True, 'cleanup_pending': False}
