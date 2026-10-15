import pytest
from app.persona_context import select_contributions
from app.materials import ContextTooLarge


def test_more_than_sixteen_authorized_notes_does_not_require_revoking_permission():
    notes=[dict(id=str(i),author_name='亲友',text='散步时候的见闻',narrative_ids=['walk']) for i in range(30)]
    wanted=dict(id='tea',author_name='女儿',text='他曾告诉我，他喜欢淡茶，但夏天也会喝白水。',narrative_ids=['tea'])
    notes.append(wanted)
    assert select_contributions(notes,'喜欢什么茶？')==[wanted]
    assert len(notes)==31


def test_relevant_notes_over_budget_ask_for_specific_question_not_less_consent():
    notes=[dict(id=str(i),author_name='亲友',text='关于淡茶的回忆') for i in range(17)]
    with pytest.raises(ContextTooLarge) as exc: select_contributions(notes,'淡茶')
    assert '具体' in str(exc.value) and '授权' not in str(exc.value)


def test_paraphrased_counterexample_and_single_character_query_are_not_lost():
    notes=[dict(id='1',author_name='女儿',text='他喜欢喝茶。'),
           dict(id='2',author_name='女儿',text='上月医生告诫后他已经改喝白水，完全戒了茶。')]
    assert select_contributions(notes,'他喜欢喝茶吗？')==notes
    assert select_contributions(notes,'茶？')==notes


def test_story_closure_preserves_correction_and_unlinked_notes():
    notes=[dict(id=str(i),author_name='友人',text='散步见闻',narrative_ids=['walk']) for i in range(20)]
    support=dict(id='tea',author_name='女儿',text='他喜欢喝茶',narrative_ids=['tea'])
    counter=dict(id='water',author_name='女儿',text='如今只喝白水',narrative_ids=['tea'])
    unlinked=dict(id='new',author_name='友人',text='医生另有叮嘱',narrative_ids=[])
    assert select_contributions(notes+[support,counter,unlinked],'喜欢喝茶')==[support,counter,unlinked]
