"""Owner-scoped historical chat recall. Summaries are hints, never person evidence."""
import hashlib
import json
import re
from uuid import uuid4
from sqlalchemy import select, delete
from .models import TwinAnswer, ChatMemoryState, ChatTurnEmbedding, ChatDigest, as_utc, utcnow
from .retrieval import _cosine, EmbeddingUnavailable
from .evidence_rag import lexical, checked_vector

MAX_RECALL_TURNS = 12
MAX_RECALL_CHARACTERS = 10000
MAX_CARRY_TURNS = 6


def is_general_overview(question):
    """Use chronological coverage only for an unqualified chat recap.

    Keeping any unknown topic/date/name/tag word makes this conservative:
    specific recall continues to use relevance, without an extra model call.
    """
    # retrieval_question appends recent topic anchors for vector search. They
    # must not turn an explicitly general current request into a topic query.
    question=question.partition('\n前文提问主题（不是本人事实）：\n')[0]
    if not re.search(r'(总结|回顾|概括).*(聊天|聊过|聊了|对话|以前|之前)|(以前|之前|过去).*(聊过什么|聊了什么|聊过哪些)',question):
        return False
    generic=('聊天记录','对话记录','以前','之前','过去','曾经','全部','所有','整体','全面',
        '总结','回顾','概括','聊过','聊了','聊天','对话','内容','记录','话题','事情','东西',
        '什么','哪些','这些','那些','我们','你们','能不能','可不可以','能否','可以','一下',
        '简单','简要','简短','大致','请','帮','给','我','你','和','的','过','了','些','把','做','都')
    rest=re.sub('|'.join(re.escape(word) for word in sorted(generic,key=len,reverse=True)),'',question)
    return not re.search(r'\w',rest)


def state(session, subject, actor):
    return session.get(ChatMemoryState, (subject, actor))


def history(session, subject, actor, basis, *, conversation_id=None):
    pref = state(session, subject, actor)
    if pref is not None and not pref.enabled:
        return []
    query = select(TwinAnswer).where(TwinAnswer.subject_id == subject,
        TwinAnswer.actor_id == actor, TwinAnswer.conversation_id.is_not(None))
    if conversation_id is not None:
        query = query.where(TwinAnswer.conversation_id == conversation_id)
    if pref is not None and pref.forgotten_before is not None:
        query = query.where(TwinAnswer.created_at > pref.forgotten_before)
    rows = session.scalars(query.order_by(TwinAnswer.created_at, TwinAnswer.answer_id)
        .execution_options(populate_existing=True))
    result = []
    for row in rows:
        valid = row.invalidated_at is None and row.source_basis == basis
        expression = row.expression or {}
        answer = (expression.get('text') if valid and row.response_type == 'SIMULATION'
                  and expression.get('status') == 'available' else row.answer) if valid else None
        result.append(dict(answer_id=row.answer_id, question=row.question, answer=answer,
            response_type=row.response_type, assistant_stale=not valid,
            created_at=as_utc(row.created_at).isoformat(), conversation_id=row.conversation_id))
    return result


def fingerprint(turns):
    return hashlib.sha256(json.dumps(turns, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def valid_recall(session, subject, actor, basis, selected, *, conversation_id=None):
    available = {t['answer_id']:t for t in history(session, subject, actor, basis, conversation_id=conversation_id)}
    return all(available.get(t['answer_id']) == t for t in selected)


def prepare(session, subject, actor, basis, question, recent, encoder, *, conversation_id=None,
            carry_latest_conversation=False):
    excluded = {t['answer_id'] for t in recent}
    turns = [t for t in history(session, subject, actor, basis, conversation_id=conversation_id) if t['answer_id'] not in excluded]
    if not turns:
        return [], [], None
    # Bound a single indexing operation explicitly, never replace all history
    # with the most recent N records without telling the caller.
    if len(turns) > 20000:
        raise EmbeddingUnavailable('旧聊天超过本次索引预算，请缩小历史范围。')
    cached = {r.answer_id:r for r in session.scalars(select(ChatTurnEmbedding).where(
        ChatTurnEmbedding.subject_id == subject, ChatTurnEmbedding.actor_id == actor,
        ChatTurnEmbedding.model_version == encoder.version))}
    documents = {t['answer_id']:t['question'] + ('\n助理此前回复（非本人事实）：'+t['answer'] if t['answer'] else '') for t in turns}
    hashes = {id:hashlib.sha256(doc.encode()).hexdigest() for id,doc in documents.items()}
    pending = [id for id in documents if id not in cached or cached[id].content_hash != hashes[id]]
    vectors = {id:r.vector for id,r in cached.items() if id in hashes and r.content_hash == hashes[id]}
    session.commit()  # no database lock across encoding/model calls
    query_vector = checked_vector(encoder.encode([question])[0])
    updates = []
    for offset in range(0, len(pending), 16):
        ids = pending[offset:offset+16]
        encoded = encoder.encode([documents[id] for id in ids])
        if len(encoded) != len(ids): raise EmbeddingUnavailable('聊天检索向量数量不一致。')
        for id, vector in zip(ids, encoded, strict=True):
            vector = checked_vector(vector)
            if len(vector) != len(query_vector): raise EmbeddingUnavailable('聊天检索向量维度不一致。')
            vectors[id] = vector
            updates.append(dict(answer_id=id, subject_id=subject, actor_id=actor,
                content_hash=hashes[id], model_version=encoder.version, vector=vector))
    scores = {}
    for id, document in documents.items():
        word = lexical(question, document)
        score = .85 * max(0., _cosine(query_vector, vectors[id])) + .15 * word
        if word >= .7: score = max(score, .5 * word)
        scores[id] = score
    ranked = sorted(turns, key=lambda t:(scores[t['answer_id']], t['created_at']), reverse=True)
    floor = max(.35, scores[ranked[0]['answer_id']] - .18)
    # A request to recap previous conversations needs topic coverage, not just
    # an embedding match to the word "chat". Keep originals from across time.
    overview = is_general_overview(question)
    if overview:
        chronological = sorted(turns, key=lambda t:(t['created_at'], t['answer_id']))
        count = min(MAX_RECALL_TURNS, len(chronological))
        ranked = [chronological[round(i*(len(chronological)-1)/max(1,count-1))] for i in range(count)]
    selected, size = [], 0
    if carry_latest_conversation:
        # A greeting need not semantically match the last call. Reserve its
        # latest tail before topic retrieval, within the same shared budget.
        # history already applies owner scope, the switch and the clear cutoff.
        latest=turns[-1]['conversation_id']
        tail=[t for t in turns if t['conversation_id']==latest][-MAX_CARRY_TURNS:]
        for turn in reversed(tail):
            needed=len(turn['question'])+len(turn['answer'] or '')
            if size+needed>MAX_RECALL_CHARACTERS:continue
            selected.append(turn);size+=needed
    selected_ids={turn['answer_id'] for turn in selected}
    for turn in ranked:
        if (not overview and scores[turn['answer_id']] < floor) or len(selected) >= MAX_RECALL_TURNS: break
        if turn['answer_id'] in selected_ids:continue
        needed = len(turn['question']) + len(turn['answer'] or '')
        if size + needed > MAX_RECALL_CHARACTERS: continue
        selected.append(turn);selected_ids.add(turn['answer_id']);size += needed
    selected.sort(key=lambda t:(t['created_at'], t['answer_id']))
    # Validate all indexed inputs at publication, including a concurrent clear.
    return selected, updates, fingerprint(turns)


def publish(session, subject, actor, basis, recent, snapshot, updates, *, conversation_id=None):
    if snapshot is None: return True
    excluded = {t['answer_id'] for t in recent}
    current = [t for t in history(session, subject, actor, basis, conversation_id=conversation_id) if t['answer_id'] not in excluded]
    if fingerprint(current) != snapshot: return False
    if session.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    for update in updates:
        statement = insert(ChatTurnEmbedding).values(**update)
        session.execute(statement.on_conflict_do_update(index_elements=['answer_id'],
            set_={k:statement.excluded[k] for k in update if k != 'answer_id'}))
    return True


def digest(session, subject, actor, selected, client):
    if not selected: return None, 'empty'
    source_hash = fingerprint(selected)
    existing = session.scalar(select(ChatDigest).where(ChatDigest.subject_id == subject,
        ChatDigest.actor_id == actor, ChatDigest.source_hash == source_hash))
    if existing:
        return dict(summary=existing.summary, source_answer_ids=existing.source_answer_ids), 'ready'
    session.commit()
    from .twin_client import TwinUnavailable
    try:
        result = client.summarize_chat(selected)
    except (AttributeError, TwinUnavailable):
        # This optional summary can fall back to exact retrieved messages.
        # Do not log message content or provider response bodies.
        return None, 'unavailable'
    if not isinstance(result, dict) or not isinstance(result.get('summary'), str) or not 0 < len(result['summary']) <= 1500:
        return None, 'unavailable'
    if not isinstance(result.get('model_version'), str) or not 0 < len(result['model_version']) <= 128:
        return None, 'unavailable'
    return dict(summary=result['summary'], source_answer_ids=[t['answer_id'] for t in selected],
        model_version=result['model_version'], source_hash=source_hash), 'generated'


def save_digest(session, subject, actor, result):
    if result is None or 'source_hash' not in result: return
    if session.scalar(select(ChatDigest).where(ChatDigest.subject_id == subject,
        ChatDigest.actor_id == actor, ChatDigest.source_hash == result['source_hash'])): return
    session.add(ChatDigest(digest_id='cd_'+uuid4().hex, subject_id=subject, actor_id=actor,
        source_hash=result['source_hash'], source_answer_ids=result['source_answer_ids'],
        summary=result['summary'], model_version=result['model_version'],
        prompt_version='chat-summary-v1', created_at=utcnow()))


def clear(session, subject, actor):
    pref = state(session, subject, actor)
    if pref is None:
        pref = ChatMemoryState(subject_id=subject, actor_id=actor, enabled=True, revision=0)
        session.add(pref)
    pref.forgotten_before = utcnow(); pref.revision += 1
    session.execute(delete(ChatTurnEmbedding).where(ChatTurnEmbedding.subject_id == subject, ChatTurnEmbedding.actor_id == actor))
    session.execute(delete(ChatDigest).where(ChatDigest.subject_id == subject, ChatDigest.actor_id == actor))
    return pref
