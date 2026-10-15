"""Explicitly permitted, signed third-party context. Never a subject fact store."""
from sqlalchemy import select
from .companion_models import CompanionContribution
from .models import Actor
from .access import is_owner
from .materials import ContextTooLarge


def visible_contributions(session,subject,actor,*,enforce_budget=True,selection_metadata=False):
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
        if selection_metadata:
            result[-1].update(narrative_ids=note.narrative_ids, status=note.status)
    # Match the private worker's complete contribution budget. Do not silently
    # drop approved notes or send a request that can only fail its input schema.
    if enforce_budget and len(result)>16:
        raise ContextTooLarge('获准用于分身回答的亲友补记超过16条，请调整补记的模型使用授权；没有截断内容。')
    if enforce_budget and sum(len(note['text'])+len(note['author_name']) for note in result)>6000:
        raise ContextTooLarge('获准用于分身回答的亲友补记正文与署名合计超过6000字符，请调整模型使用授权；没有截断内容。')
    return result


def select_contributions(notes,question):
    """Select whole authorized notes; a growing archive never changes consent."""
    def fits(items):
        return len(items)<=16 and sum(len(n['text'])+len(n['author_name']) for n in items)<=6000
    if fits(notes): return notes
    def terms(text):
        import re
        text=''.join(re.findall(r'[\w\u4e00-\u9fff]+',text.lower()))
        return {text[i:i+2] for i in range(len(text)-1)} if len(text)>1 else set(text)
    query=terms(question)
    ranked=[(len(query & terms(n['text']+' '+n['author_name'])),n) for n in notes]
    seeds=[n for score,n in ranked if score>0]
    # Story links are reviewed data, not a guessed semantic equivalence. Keep
    # every linked perspective, unresolved disagreement and unlinked note: the
    # latter cannot safely be ruled out by lexical non-match.
    selected={n['id'] for n in seeds}
    selected.update(n['id'] for n in notes if not n.get('narrative_ids') or n.get('status')=='disagreement')
    changed=True
    while changed:
        groups={g for n in notes if n['id'] in selected for g in n.get('narrative_ids',[])}
        expanded=selected | {n['id'] for n in notes if groups.intersection(n.get('narrative_ids',[]))}
        changed=expanded!=selected;selected=expanded
    relevant=[n for n in notes if n['id'] in selected]
    # Preserve all relevant perspectives. A budget conflict asks for a narrower
    # question, never for withdrawing anybody's authorization.
    if not fits(relevant):
        raise ContextTooLarge('与本题相关的亲友补记较多，请把问题问得更具体一些。')
    return relevant
