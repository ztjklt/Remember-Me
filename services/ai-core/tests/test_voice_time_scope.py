"""The reported tea-time follow-up must not quote a taste as a time."""
import pytest
from app.quoted_twin import QuotedTwin
from test_voice_original_proposal import Chat, payload, verdict


@pytest.mark.parametrize('source', ['我喝茶喜欢淡一点，太甜的我喝不惯。',
    '我喜欢淡茶，太浓的喝不惯，但客人喜欢浓茶也随他。'])
def test_unknown_tea_time_is_proposed_before_one_full_review(source):
    p = payload('你一般什么时候喝茶？', source)
    chat = Chat(verdict())
    result = QuotedTwin(chat).answer(p)
    assert result.response_type == 'UNKNOWN'
    assert result.answer == '这个我还说不准。'
    assert len(chat.requests) == 1
    packet = chat.requests[0][1]
    assert packet['selection']['points'][0]['known'] is False
    assert packet['recordings'][0]['sources'][0]['text'] == p.candidates[0].evidence[0].excerpt


def test_unknown_is_not_accepted_when_reviewer_finds_a_known_time_elsewhere():
    p = payload('你一般什么时候喝茶？')
    other = p.candidates[0].model_copy(deep=True)
    other.memory_item_id='m2';other.evidence[0].evidence_id='e2';other.evidence[0].episode_id='ep2'
    other.evidence[0].excerpt='下午吃过点心，我会泡上一杯。'
    other.evidence[0].span_end=len(other.evidence[0].excerpt)
    p.candidates.append(other)
    chat = Chat(verdict(False, {'points':[{'known':True,'source_ids':['s2']}]}), verdict())
    result = QuotedTwin(chat).answer(p)
    assert len(chat.requests)==2 and result.evidence_ids==['e2']
    assert len(chat.requests[0][1]['recordings'])==2


def test_followup_filler_does_not_select_unrelated_timed_activity():
    p = payload('那你一般什么时候喝？', '我喜欢淡茶，喝不惯太浓的。')
    other = p.candidates[0].model_copy(deep=True)
    other.memory_item_id='m2';other.evidence[0].evidence_id='e2';other.evidence[0].episode_id='ep2'
    other.evidence[0].excerpt='那年退休以后，我一般下午三点出去散步。'
    other.evidence[0].span_end=len(other.evidence[0].excerpt)
    p.candidates.insert(0, other)
    chat=Chat(verdict())
    result=QuotedTwin(chat).answer(p)
    assert result.response_type=='UNKNOWN'
    assert len(chat.requests)==1 and len(chat.requests[0][1]['recordings'])==2


def test_explicit_time_and_year_remain_quoted_and_reviewed():
    for question, text in [('什么时候喝茶？','我一般下午三点喝茶。'),
                           ('第一次独立开车是哪一年？','第一次独立开车是1987年，不是1986年。')]:
        chat=Chat(verdict());result=QuotedTwin(chat).answer(payload(question,text))
        assert result.response_type=='ORIGINAL' and result.answer==text
        assert len(chat.requests)==1


def test_no_evidence_voice_reply_is_plain_but_does_not_invent():
    p=payload();p.candidates=[]
    result=QuotedTwin(Chat()).answer(p)
    assert result.answer=='这个我还说不准。' and result.evidence_ids==[]
