"""Zero-LLM entry points: selected evidence plus exact recipient, never secret text."""
import hashlib
import json
from sqlalchemy import select
from .access import is_owner
from .companion_models import CompanionLetter, LetterRecallCue
from .models import Subject, Episode
from .narrative import material_map


def selected_source_basis(session, subject_id, evidence_ids, *, sources=None):
    """Only the explicitly selected, still-active originals define this cue.

    Answer freshness and recipient grants are independently checked by the
    answer/open endpoints. New unrelated memories must not undo owner intent.
    """
    subject=session.get(Subject,subject_id)
    if subject is None or not subject.owner_actor_id: return None
    if sources is None: sources=material_map(session,subject_id,subject.owner_actor_id)
    selected={}
    for eid in sorted(evidence_ids):
        source=sources.get(eid)
        if source is None: return None
        episode=session.get(Episode,source['episode_id'])
        if episode is None or episode.status!='ready': return None
        selected[eid]={'source':source,'transcript':episode.transcript,
            'audio_checksum':episode.audio_checksum,'actor_id':episode.actor_id}
    return hashlib.sha256(json.dumps({'version':'recall-selected-evidence-v1',
        'sources':selected},ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def recall_actions(session, answer):
    if answer.invalidated_at is not None or answer.response_type == 'UNKNOWN' or not answer.evidence_ids:
        return []
    rows=session.execute(select(CompanionLetter,LetterRecallCue).join(
        LetterRecallCue,LetterRecallCue.letter_id==CompanionLetter.id).where(
        CompanionLetter.subject_id==answer.subject_id,CompanionLetter.status=='published')).all()
    owner=is_owner(session,answer.subject_id,answer.actor_id) if rows else False
    sources=None
    result=[]
    for letter,cue in rows:
        if not (owner or letter.recipient_actor_id==answer.actor_id): continue
        if not set(cue.evidence_ids).intersection(answer.evidence_ids): continue
        if cue.letter_revision!=letter.revision: continue
        if sources is None:
            subject=session.get(Subject,answer.subject_id)
            sources=material_map(session,answer.subject_id,subject.owner_actor_id) if subject else {}
        if cue.source_version!=selected_source_basis(session,answer.subject_id,cue.evidence_ids,sources=sources): continue
        result.append(dict(letter_id=letter.id, label='打开那封信',
                           prompt='这里还留着一段话。', has_audio=bool(letter.audio_id)))
    return result[:3]
