"""Failure diagnostics expose fixed categories, never source/model text."""
import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import AIOutputInvalid
from app.persona import PersonaInput, PersonaProvider
from test_persona import ScriptedChat, payload, point, review


def test_schema_repair_gets_safe_field_diagnostics_and_keeps_both_failures(caplog):
    draft = {'points':[point()]}
    del draft['points'][0]['contribution_ids']
    draft['points'][0]['PRIVATE_UNKNOWN_FIELD'] = 'PRIVATE_GENERATED_TEXT'
    chat = ScriptedChat(draft,draft)
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(payload()))
    correction = chat.requests[1][1]['validation_error']
    assert correction['category'] == 'draft_schema'
    assert {'type':'missing','loc':['points',0,'contribution_ids']} in correction['schema_issues']
    assert {'type':'extra_forbidden','loc':['points',0,'?']} in correction['schema_issues']
    logs = [json.loads(r.message) for r in caplog.records if r.message.startswith('{')]
    events = [r for r in logs if r.get('event')=='persona_validation']
    assert [r['stage'] for r in events] == ['generation_validation','generation_repair']
    assert all(r['category']=='draft_schema' for r in events)
    assert 'PRIVATE_UNKNOWN_FIELD' not in caplog.text and 'PRIVATE_GENERATED_TEXT' not in caplog.text
    assert len(chat.requests)==2


@pytest.mark.parametrize('changes,category', [
    ({'source_ids':['wrong']},'source_identity'),
    ({'understanding_ids':['wrong']},'understanding_identity'),
    ({'contribution_ids':['wrong']},'contribution_identity'),
    ({'mode':'UNKNOWN','text':'PRIVATE_PROMISE','understanding_ids':[]},'unknown_contains_claims'),
])
def test_reference_categories_are_distinct_and_do_not_weaken_validation(caplog,changes,category):
    draft={'points':[point(**changes)]}; chat=ScriptedChat(draft,draft)
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(payload()))
    assert chat.requests[1][1]['validation_error']['category']==category
    assert 'PRIVATE_PROMISE' not in caplog.text


def test_actual_asr_name_difference_cannot_be_normalized_into_subject_name(caplog):
    data=payload()
    data['contributions']=[{'id':'contribution-real','author_name':'A01 亲友体验','classification':'firsthand',
        'text':'这不是陈国良本人的原话。这只是我的一次观察，不能说他每次都这样。'}]
    draft={'points':[point(mode='ATTRIBUTED',text='陈国梁重视旧物。',understanding_ids=[],
        contribution_ids=['c1'],names=['陈国梁'])]}
    chat=ScriptedChat(draft,draft)
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(data))
    assert chat.requests[1][1]['validation_error']['category']=='name_source_mismatch'
    assert '陈国梁' not in caplog.text and '陈国良' not in caplog.text


def test_author_prefix_is_included_in_answer_character_budget(caplog):
    data=payload(); data['contributions'][0]['author_name']='名'*128
    data['contributions'][0]['text']='观'*350
    contribution=point(mode='ATTRIBUTED',text='观'*350,understanding_ids=[],contribution_ids=['c1'])
    fact=point(mode='FACT',text='平常我会先问清安排，再决定。'*2,source_ids=['s1'],understanding_ids=[])
    draft={'points':[contribution,fact]}; chat=ScriptedChat(draft,draft)
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(data))
    error=chat.requests[1][1]['validation_error']
    assert error['category']=='answer_character_budget' and error['answer_characters']>500
    assert error['maximum']==500


def test_all_trait_support_and_counterexamples_still_count_toward_evidence_limit():
    data=payload()
    data['candidates'][0]['evidence'] += [dict(evidence_id=f'e{i}',excerpt='例外。',source_type='SUBJECT') for i in range(4,10)]
    data['understandings'][0]['counter_evidence_ids']=[f'e{i}' for i in range(2,10)]
    draft={'points':[point()]}; chat=ScriptedChat(draft,draft)
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(data))
    assert chat.requests[1][1]['validation_error']=={'category':'evidence_count_budget','evidence_count':9,'maximum':8}


def test_fictional_trace_defaults_off_and_is_forbidden_in_nonlocal_environments():
    assert not Settings(_env_file=None).persona_fictional_debug_trace
    for environment in ['production','staging']:
        with pytest.raises(ValidationError):
            Settings(_env_file=None,environment=environment,persona_fictional_debug_trace=True)


def test_opt_in_trace_captures_draft_and_review_only_in_fixed_debug_directory(monkeypatch,tmp_path,caplog):
    import app.persona as module
    monkeypatch.setattr(module,'FICTIONAL_TRACE_DIR',tmp_path)
    draft={'points':[point()]}
    PersonaProvider(ScriptedChat(draft,review())).answer(PersonaInput.model_validate(payload()))
    assert list(tmp_path.iterdir())==[]
    PersonaProvider(ScriptedChat(draft,review()),fictional_debug_trace=True).answer(PersonaInput.model_validate(payload()))
    assert len(list(tmp_path.glob('*.json')))==2
    files=list(tmp_path.glob('*-generation_validation.json')); assert len(files)==1
    captured=json.loads(files[0].read_text(encoding='utf8'))
    assert captured['draft']==draft and captured['fictional_debug_only'] is True
    assert 'packet' not in captured and 'api_key' not in captured
    checked=json.loads(next(tmp_path.glob('*-semantic_review.json')).read_text(encoding='utf8'))
    assert checked['review']==review() and 'packet' not in checked and 'api_key' not in checked
    assert point()['text'] not in caplog.text


def test_attribution_prompt_uses_exact_array_field_and_repair_still_needs_review():
    from app.persona import SYSTEM
    assert 'contribution_ids数组' in SYSTEM
    assert 'contribution_id字段' in SYSTEM
    bad={'points':[point(understanding_ids=['wrong'])]}
    chat=ScriptedChat(bad,{'points':[point()]},review(False,['unsupported']))
    with pytest.raises(AIOutputInvalid): PersonaProvider(chat).answer(PersonaInput.model_validate(payload()))
    assert len(chat.requests)==3
