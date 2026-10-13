"""Explicitly permitted, signed third-party context. Never a subject fact store."""
from sqlalchemy import select
from .companion_models import CompanionContribution
from .models import Actor
from .access import is_owner
from .materials import ContextTooLarge


def visible_contributions(session,subject,actor):
    result=[]
    for note in session.scalars(select(CompanionContribution).where(
            CompanionContribution.subject_id==subject,
            CompanionContribution.status.in_(['accepted','disagreement']),
            CompanionContribution.model_use_author_allowed==True,
            CompanionContribution.model_use_owner_allowed==True)):
        if not (is_owner(session,subject,actor) or actor==note.author_actor_id or actor in note.recipient_actor_ids): continue
        author=session.get(Actor,note.author_actor_id)
        result.append(dict(id=note.id,author_name=author.display_name if author else '亲友',
            classification=note.classification,text=note.text))
    # Match the private worker's complete contribution budget. Do not silently
    # drop approved notes or send a request that can only fail its input schema.
    if len(result)>16:
        raise ContextTooLarge('获准用于分身回答的亲友补记超过16条，请调整补记的模型使用授权；没有截断内容。')
    if sum(len(note['text'])+len(note['author_name']) for note in result)>6000:
        raise ContextTooLarge('获准用于分身回答的亲友补记正文与署名合计超过6000字符，请调整模型使用授权；没有截断内容。')
    return result
