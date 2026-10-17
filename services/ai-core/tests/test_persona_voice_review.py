"""A shorter wire format must preserve all semantic decisions and source data."""
import json

import pytest

from app.errors import AIOutputInvalid
from app.persona import PersonaInput, PersonaProvider
from test_persona import ScriptedChat, payload, point, review


def compact(**changes):
    value={'v':'supported','e':[],'r':'u1及反例s2支持，限定未丢。',
           'c':'complete','ce':[],'m':[],'cr':'已回答本轮问题。'}
    value.update(changes)
    return value


def voice_payload():
    value=payload();value['voice_response']=True
    value['question']='遇到平常的临时安排，你会怎么办？'
    return PersonaInput.model_validate(value)


def test_single_voice_short_review_keeps_full_material_and_exact_point_view():
    chat=ScriptedChat({'points':[point()]},compact())
    result=PersonaProvider(chat).answer(voice_payload())
    request=chat.requests[1][1]
    assert set(request['response_schema']['properties'])=={'v','e','r','c','ce','m','cr'}
    assert request['review_scope'][0]['rendered_text']==result.answer
    assert request['cited_material'][0]['source_ids']==['s1','s2']
    assert request['cited_material'][0]['understanding_ids']==['u1']
    assert request['understandings'][0]['counter_source_ids']==['s2']
    assert sum(len(r['sources']) for r in request['recordings'])==3 and len(request['contributions'])==1
    # Keep even uncited material for conflict/UNKNOWN/coverage checks, exactly once.
    text=json.dumps(request,ensure_ascii=False)
    assert text.count('如果家里有急事，我也会先去处理。')==1
    assert 'rendered_answer' not in request
    assert 'text' not in request['draft']['points'][0]
    assert result.evidence_ids==['e1','e2'] and len(chat.requests)==2


@pytest.mark.parametrize('change',[
    {'v':'unsupported','e':['new_commitment']},
    {'v':'uncertain','e':['counterexample']},
    {'v':'supported','e':['unsupported']},
    {'c':'partial','ce':['incomplete'],'m':[]},
    {'extra':'do not silently ignore'},
    {'r':''},
])
def test_short_review_never_turns_negative_or_malformed_output_into_acceptance(change):
    chat=ScriptedChat({'points':[point()]},compact(**change))
    with pytest.raises(AIOutputInvalid):PersonaProvider(chat).answer(voice_payload())
    assert len(chat.requests)==2


def test_short_review_missing_verdict_has_no_default():
    verdict=compact();del verdict['v']
    chat=ScriptedChat({'points':[point()]},verdict)
    with pytest.raises(AIOutputInvalid):PersonaProvider(chat).answer(voice_payload())


def test_multiple_voice_points_keep_independent_verdicts_and_dependency_graph():
    first=point();second=point(question_part='另一个要点')
    chat=ScriptedChat({'points':[first,second]},review(count=2))
    result=PersonaProvider(chat).answer(voice_payload())
    assert set(chat.requests[1][1]['response_schema']['properties'])=={'points','coverage'}
    assert result.coverage=='complete'


def test_voice_condition_uses_situation_not_a_required_hedging_phrase():
    chat=ScriptedChat({'points':[point()]},review())
    PersonaProvider(chat).answer(voice_payload())
    generation=chat.requests[0][0];review_system=chat.requests[1][0]
    assert '不要求固定' in generation and '换作我' in generation
    assert '问题已明确假设情境' in review_system
    assert '不得制造经历' in review_system
