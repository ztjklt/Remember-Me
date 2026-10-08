"""User language explanations keep provenance distinct from recorded speech."""
import hashlib
from sqlalchemy import select, func
from .models import Evidence, MemoryItem, MemoryRevision


def is_owner_supplement(memory):
    return ((memory.item_metadata or {}).get('origin') == 'owner_supplement'
            and memory.model_version == 'owner-input'
            and memory.memory_item_id.startswith('note_'))


def store_supplement(session, episode):
    text = (episode.capture_metadata or {}).get('review_supplement', '').strip()
    if not text:
        return
    digest = hashlib.sha256(episode.episode_id.encode()).hexdigest()[:36]
    mid, eid = 'note_'+digest, 'ev_note_'+digest
    # A retry must never duplicate or resurrect a deleted manual note.
    if session.get(MemoryItem, mid) is not None:
        return
    session.add(Evidence(evidence_id=eid, episode_id=episode.episode_id,
        source_type='CALIBRATION', source_ref='owner-supplement:'+episode.episode_id,
        excerpt=text, span_start=None, span_end=None, confidence=1.0))
    ordinal = session.scalar(select(func.max(MemoryItem.ordinal)).where(MemoryItem.episode_id==episode.episode_id))
    revision = session.scalar(select(MemoryRevision).where(MemoryRevision.episode_id==episode.episode_id))
    session.add(MemoryItem(memory_item_id=mid,episode_id=episode.episode_id,
        ordinal=0 if ordinal is None else ordinal+1, memory_type='EVENT', content=text,
        source_type='CALIBRATION', evidence_ids=[eid], confidence=1.0,
        model_version='owner-input', prompt_version='owner-supplement-v1', schema_version='0.2.0',
        item_metadata={'origin':'owner_supplement','domain':'EPISODIC_MEMORY',
                       'reviewed_by':episode.transcript_reviewed_by}, review_state='pending' if revision and revision.status=='pending' else 'active'))
    session.flush()
