import pytest
from app.persona_context import select_contributions
from app.materials import ContextTooLarge


def test_more_than_sixteen_authorized_notes_does_not_require_revoking_permission():
    notes=[dict(id=str(i),author_name='亲友',text='散步时候的见闻') for i in range(30)]
    wanted=dict(id='tea',author_name='女儿',text='他曾告诉我，他喜欢淡茶，但夏天也会喝白水。')
    notes.append(wanted)
    assert select_contributions(notes,'喜欢什么茶？')==[wanted]
    assert len(notes)==31


def test_relevant_notes_over_budget_ask_for_specific_question_not_less_consent():
    notes=[dict(id=str(i),author_name='亲友',text='关于淡茶的回忆') for i in range(17)]
    with pytest.raises(ContextTooLarge) as exc: select_contributions(notes,'淡茶')
    assert '具体' in str(exc.value) and '授权' not in str(exc.value)
