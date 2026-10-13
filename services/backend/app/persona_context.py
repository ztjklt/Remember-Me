"""Explicitly permitted persona context and its private worker budgets."""
import json
from sqlalchemy import select
from .companion_models import CompanionContribution
from .models import Actor
from .access import is_owner
from .materials import ContextTooLarge


def require_persona_budget(payload):
    """Reject complete oversized context before transport, never trim evidence.

    Mirrors PersonaInput's existing private budgets, not the public Contract.
    A schema rejection by AI Core otherwise becomes a retryable transport error.
    """
    examples = payload['examples']
    if (len(examples) > 8 or sum(len(e['text']) for e in examples) > 4000
            or any(len(e['text']) > 1500 for e in examples)):
        raise ContextTooLarge('本次分身表达范例超过8条或4000字符，请减少已启用的范例，或切换记录问答；没有截断原文。')
    understandings = payload['understandings']
    if (len(understandings) > 32
            or sum(len(u['statement']) + len(u['context']) for u in understandings) > 12000
            or any(len(u['statement']) > 1000 or len(u['context']) > 1000
                   or len(u['evidence_ids']) > 32 or len(u['counter_evidence_ids']) > 32
                   for u in understandings)):
        raise ContextTooLarge('本次分身理解超过32条或12000字符，请调整参与回答的已确认理解，或切换记录问答；没有删除来源或例外。')
    candidates = payload['candidates']
    evidence = [e for c in candidates for e in c['evidence']]
    originals = {e['evidence_id']: e['excerpt'] for e in evidence}
    if (len(candidates) > 256 or len(evidence) > 1024 or len(originals) > 256
            or sum(map(len, originals.values())) > 24000):
        raise ContextTooLarge('本次分身原文超过处理范围，请缩小故事范围或使用记录问答；没有截断证据。')
    # AI Core counts its parsed model, including defaults absent on written
    # corrections. Count a copy with those defaults; never rewrite the source.
    normalized = {**payload, 'candidates': [
        {'domain': None, 'unresolved': False, 'traits': [], 'graph_facts': [], **c,
         'evidence': [{'episode_id': None, 'recorded_at': None, 'span_start': None,
                       'span_end': None, 'temporal_context': '', **e}
                      for e in c['evidence']]} for c in candidates]}
    for candidate in normalized['candidates']:
        for source in candidate['evidence']:
            recorded_at = source['recorded_at']
            if isinstance(recorded_at, str) and recorded_at.endswith('+00:00'):
                source['recorded_at'] = recorded_at[:-6] + 'Z'
    if len(json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))) > 120000:
        raise ContextTooLarge('本次分身完整上下文超过120000字符，请减少参与回答的理解和范例；没有截断内容。')


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
