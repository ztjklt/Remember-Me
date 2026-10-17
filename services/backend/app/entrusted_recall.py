"""Zero-LLM entry points: selected evidence plus exact recipient, never secret text."""
from sqlalchemy import select
from .access import source_basis, is_owner
from .companion_models import CompanionLetter, LetterRecallCue


def recall_actions(session, answer):
    if answer.invalidated_at is not None or answer.response_type == 'UNKNOWN' or not answer.evidence_ids:
        return []
    rows=session.execute(select(CompanionLetter,LetterRecallCue).join(
        LetterRecallCue,LetterRecallCue.letter_id==CompanionLetter.id).where(
        CompanionLetter.subject_id==answer.subject_id,CompanionLetter.status=='published')).all()
    current=source_basis(session,answer.subject_id) if rows else ''
    owner=is_owner(session,answer.subject_id,answer.actor_id) if rows else False
    result=[]
    for letter,cue in rows:
        if not (owner or letter.recipient_actor_id==answer.actor_id): continue
        if cue.source_version!=current or cue.letter_revision!=letter.revision: continue
        if not set(cue.evidence_ids).intersection(answer.evidence_ids): continue
        result.append(dict(letter_id=letter.id, label='打开那封信',
                           prompt='这里还留着一段话。', has_audio=bool(letter.audio_id)))
    return result[:3]
