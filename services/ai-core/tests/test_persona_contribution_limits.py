"""Contribution storage size and worker context budget are intentionally separate."""
import pytest
from pydantic import ValidationError
from app.persona import PersonaInput


def payload(notes):
    return {'question':'如何考虑','candidates':[],'understandings':[],'examples':[],
        'contributions':[{'id':'c'+str(i),'author_name':'作者','classification':'opinion','text':text}
                         for i,text in enumerate(notes)]}


def test_long_saved_note_is_accepted_without_truncation_within_total_budget():
    text='亲'*5000
    parsed=PersonaInput.model_validate(payload([text]))
    assert parsed.contributions[0].text==text


def test_total_budget_includes_author_names_and_keeps_six_thousand_limit():
    assert len(PersonaInput.model_validate(payload(['亲'*2998,'亲'*2998])).contributions)==2
    with pytest.raises(ValidationError,match='Contribution budget exceeded'):
        PersonaInput.model_validate(payload(['亲'*2999,'亲'*2999]))
