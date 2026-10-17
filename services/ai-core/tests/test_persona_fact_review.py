"""Specialized fact review must keep all evidence and reject the same hard failures."""
import pytest
from app.errors import AIOutputInvalid
from app.persona import PersonaInput, PersonaProvider, REVIEW_SYSTEM, SYSTEM
from test_persona import payload, point, ScriptedChat, review


def fact_input():
    data=payload();data.update(voice_response=True,understandings=[],contributions=[],examples=[])
    data['question']='你平常怎么处理安排？'
    return PersonaInput.model_validate(data)


def fact():
    return point(mode='FACT',text='平常我会先问清安排，再决定。',source_ids=['s1'],understanding_ids=[])


def test_fact_only_review_shortens_instructions_without_losing_uncited_sources():
    chat=ScriptedChat({'points':[fact()]},review())
    result=PersonaProvider(chat).answer(fact_input())
    system,request=chat.requests[1]
    assert len(system)<len(REVIEW_SYSTEM)
    assert request['review_scope'][0]['rendered_text']==result.answer
    assert sum(len(r['sources']) for r in request['recordings'])==3
    assert request['cited_material'][0]['source_ids']==['s1']
    assert result.evidence_ids==['e1'] and len(chat.requests)==2


def test_fact_only_generation_uses_shorter_instructions_and_keeps_source_packet():
    chat=ScriptedChat({'points':[fact()]},review())
    PersonaProvider(chat).answer(fact_input())
    system,request=chat.requests[0]
    assert len(system)<len(SYSTEM)
    assert sum(len(r['sources']) for r in request['recordings'])==3
    assert request['understandings']==[] and request['contributions']==[]


@pytest.mark.parametrize('code',['new_commitment','attribution','context','names','uncertainty','time','irrelevant','instructions'])
def test_specialized_review_never_overrides_a_negative_verdict(code):
    chat=ScriptedChat({'points':[fact()]},review(False,[code]))
    with pytest.raises(AIOutputInvalid):PersonaProvider(chat).answer(fact_input())
    assert len(chat.requests)==2


def test_third_party_material_and_conditional_simulation_keep_full_review():
    data=fact_input();data.candidates[0].evidence[2].source_type='THIRD_PARTY'
    chat=ScriptedChat({'points':[fact()]},review())
    PersonaProvider(chat).answer(data)
    assert REVIEW_SYSTEM in chat.requests[1][0]
    data=PersonaInput.model_validate(dict(payload(),voice_response=True))
    chat=ScriptedChat({'points':[point()]},review())
    PersonaProvider(chat).answer(data)
    assert REVIEW_SYSTEM in chat.requests[1][0]
