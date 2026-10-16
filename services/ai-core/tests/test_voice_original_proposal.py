import pytest

from app.errors import AIOutputInvalid
from app.quoted_twin import QuotedTwin
from app.twin import TwinInput


def payload(question='你喜欢什么茶？', text='我喜欢淡茶，太浓的喝不惯，但客人喜欢浓茶也随他。'):
    return TwinInput(question=question, voice_response=True, candidates=[dict(
        memory_item_id='m1', statement='不可用来回答的摘要', evidence=[dict(
            evidence_id='e1', excerpt=text, source_type='SUBJECT', episode_id='ep1',
            span_start=0, span_end=len(text), recorded_at='2026-10-01T00:00:00Z')])])


def verdict(valid=True, replacement=None):
    return dict(reasoning='Check the full source and question.', valid=valid,
                failure_codes=[] if valid else ['irrelevant'], replacement=replacement)


class Chat:
    def __init__(self, *replies):
        self.replies=iter(replies); self.requests=[]

    def complete(self, system, packet):
        self.requests.append((system, packet))
        return next(self.replies), 'actual-review-model'


def test_direct_original_uses_one_full_review_and_its_actual_model_version():
    p=payload(); chat=Chat(verdict())
    answer=QuotedTwin(chat).answer(p)
    assert len(chat.requests)==1
    assert answer.answer==p.candidates[0].evidence[0].excerpt
    assert answer.evidence_ids==['e1'] and answer.response_type=='ORIGINAL'
    assert answer.model_version=='actual-review-model'
    request=chat.requests[0][1]
    assert request['cited_material'][0]['sources'][0]['text']==answer.answer
    assert request['question_context_policy']['unresolved_referent_is_unknown']


def test_direct_and_selected_identical_quote_get_identical_review_prompt_and_material():
    p=payload(); direct=Chat(verdict())
    selected=Chat({'points':[{'known':True,'source_ids':['s1']}]}, verdict())
    assert QuotedTwin(direct).answer(p)==QuotedTwin(selected, direct_original=False).answer(p)
    assert direct.requests[0]==selected.requests[1]


@pytest.mark.parametrize('question', ['刚才说的茶，你喜欢浓一点还是淡一点？',
                                    '关于茶，你喜欢浓一点还是淡一点？'])
def test_explicit_topic_comma_does_not_add_a_selection_call(question):
    p=payload(question); chat=Chat(verdict())
    answer=QuotedTwin(chat).answer(p)
    assert len(chat.requests)==1 and answer.evidence_ids==['e1']
    assert chat.requests[0][1]['question']==question


def test_topic_prefix_does_not_hide_a_second_question():
    p=payload('关于茶，你喜欢什么茶，母亲在哪里工作？')
    chat=Chat({'points':[{'known':False,'source_ids':[]}]}, verdict())
    QuotedTwin(chat).answer(p)
    assert 'selection' not in chat.requests[0][1] and len(chat.requests)==2


def test_broad_preference_policy_is_shared_without_inventing_missing_details():
    chat=Chat({'points':[{'known':True,'source_ids':['s1']}]}, verdict())
    QuotedTwin(chat,direct_original=False).answer(payload())
    for system, _ in chat.requests:
        assert '开放式偏好' in system and '明确限定' in system


def test_review_shape_repair_retains_question_and_reference_rules():
    incomplete=verdict();incomplete.pop('replacement')
    chat=Chat(incomplete,verdict())
    QuotedTwin(chat).answer(payload())
    assert chat.requests[1][0].startswith(chat.requests[0][0])


def test_reviewer_sees_conflicting_full_source_and_can_replace_then_recheck():
    p=payload(); other=p.candidates[0].model_copy(deep=True)
    other.memory_item_id='m2'; other.evidence[0].evidence_id='e2'; other.evidence[0].episode_id='ep2'
    other.evidence[0].excerpt='之前讲淡茶，但我现在喜欢红茶。'
    other.evidence[0].span_end=len(other.evidence[0].excerpt); p.candidates.append(other)
    chat=Chat(verdict(False, {'points':[{'known':True,'source_ids':['s2']}]}), verdict())
    answer=QuotedTwin(chat).answer(p)
    assert answer.evidence_ids==['e2'] and len(chat.requests)==2
    assert len(chat.requests[0][1]['recordings'])==2
    assert chat.requests[1][1]['cited_material'][0]['sources'][0]['id']=='s2'


def test_negative_proposal_can_fall_back_but_cannot_revote_unchanged_answer():
    chat=Chat(verdict(False), {'points':[{'known':True,'source_ids':['s1']}]}, verdict())
    with pytest.raises(AIOutputInvalid): QuotedTwin(chat).answer(payload())
    assert len(chat.requests)==2


def test_changed_fallback_still_requires_full_review():
    chat=Chat(verdict(False), {'points':[{'known':False,'source_ids':[]}]}, verdict(False))
    with pytest.raises(AIOutputInvalid): QuotedTwin(chat).answer(payload())
    assert len(chat.requests)==3
    assert chat.requests[-1][1]['selection']['points'][0]['known'] is False


def test_same_negative_replacement_is_not_a_second_vote():
    chat=Chat(verdict(False, {'points':[{'known':True,'source_ids':['s1']}]}), verdict())
    with pytest.raises(AIOutputInvalid): QuotedTwin(chat).answer(payload())
    assert len(chat.requests)==1


@pytest.mark.parametrize('question', ['为什么喜欢淡茶？','如果没有淡茶怎么办？',
    '请讲讲喝茶的故事。','你第一次参加这种活动是哪一年？','喜欢什么茶，母亲在哪里工作？'])
def test_complex_or_unresolved_questions_keep_selection_and_review(question):
    chat=Chat({'points':[{'known':False,'source_ids':[]}]}, verdict())
    QuotedTwin(chat).answer(payload(question))
    assert 'selection' not in chat.requests[0][1] and len(chat.requests)==2


def test_written_material_and_oversized_sources_do_not_become_original_proposals():
    for p in [payload(text='我喜欢淡茶。'*80), payload()]:
        if len(p.candidates[0].evidence[0].excerpt)<380:
            p.candidates[0].evidence[0].source_type='CALIBRATION'
        chat=Chat({'points':[{'known':False,'source_ids':[]}]}, verdict())
        QuotedTwin(chat).answer(p)
        assert 'selection' not in chat.requests[0][1]


def test_private_preparation_never_releases_rejected_proposal():
    from app.voice_stream import voice_response
    import asyncio, json
    async def run():
        chat=Chat(verdict(False), {'points':[{'known':True,'source_ids':['s1']}]})
        return [json.loads(line) async for line in voice_response(
            lambda: QuotedTwin(chat).answer(payload())).body_iterator]
    events=asyncio.run(run())
    assert events[0]['type']=='draft'  # Private API-to-AI stream only.
    assert events[-1]['type']=='error' and not any(e['type']=='final' for e in events)
