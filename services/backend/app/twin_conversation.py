"""Only server-owned, actor/subject-scoped turns form a conversation."""
from sqlalchemy import select
from .access import Hidden
from .models import TwinAnswer

MAX_TURNS = 20
MAX_CHARACTERS = 24000


def context(session, subject_id, actor_id, parent_id, current_basis):
    rows, seen, size, truncated = [], set(), 0, False
    conversation_id = None
    while parent_id:
        if parent_id in seen:
            raise Hidden('会话链不可用，请开始新的聊天。')
        if len(rows) >= MAX_TURNS:
            truncated = True
            break
        seen.add(parent_id)
        row = session.scalar(select(TwinAnswer).where(TwinAnswer.answer_id == parent_id,
            TwinAnswer.subject_id == subject_id, TwinAnswer.actor_id == actor_id))
        if row is None:
            raise Hidden('前一条消息不属于当前本人会话。')
        cid = row.conversation_id or ('tc_' + row.answer_id)
        if conversation_id is None: conversation_id = cid
        elif row.conversation_id is not None and row.conversation_id != conversation_id:
            raise Hidden('会话链不可用，请开始新的聊天。')
        # Expired assistant text cannot smuggle deleted evidence back in.
        valid = row.invalidated_at is None and row.source_basis == current_basis
        expression = row.expression or {}
        answer = expression.get('text') if valid and row.response_type == 'SIMULATION' and expression.get('status') == 'available' else row.answer
        answer = answer if valid else None
        needed = len(row.question) + len(answer or '')
        if size + needed > MAX_CHARACTERS:
            truncated = True
            break
        size += needed
        rows.append({'answer_id': row.answer_id, 'question': row.question,
                     'answer': answer, 'response_type': row.response_type,
                     'assistant_stale': not valid})
        parent_id = row.parent_answer_id
    return list(reversed(rows)), conversation_id, truncated


def retrieval_question(question, turns):
    if not turns: return question
    # Topic anchors aid retrieval; generation/review still see the actual
    # question and full bounded dialogue. No invented standalone question.
    anchors = '\n'.join(t['question'] for t in reversed(turns[-4:]))
    return (question + '\n前文提问主题（不是本人事实）：\n' + anchors)[:1000]
