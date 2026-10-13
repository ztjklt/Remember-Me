from app.twin import TwinInput
from app.providers.weixin import compact_twin_materials
import pytest
from pydantic import ValidationError


def test_chronological_groups_keep_pronoun_context_despite_relevance_sort():
    texts = [('old', '2026-09-27T02:00:00+00:00', 0, '这个原因我还没说。'),
             ('new', '2026-09-30T02:00:00+00:00', 0, '今天来回答上次的问题。'),
             ('new', '2026-09-30T02:00:00+00:00', 12, '因为有人为我留着灯。')]
    payload = TwinInput(question='为什么留着灯？', candidates=[
        dict(memory_item_id=str(i), statement=t, evidence=[dict(evidence_id=f'ev{i}',
            excerpt=t, source_type='SUBJECT', episode_id=ep, recorded_at=date,
            span_start=start, span_end=start+len(t), temporal_context='')])
        for i, (ep,date,start,t) in enumerate(texts)])
    compact, aliases = compact_twin_materials(payload)
    assert compact['sources'][0]['evidence_id'] == 's3'
    assert [(g['episode_id'], g['source_ids']) for g in compact['recordings']] == [
        ('old', ['s1']), ('new', ['s2','s3'])]
    assert compact['recordings'][1]['recorded_at'].startswith('2026-09-30')
    assert aliases == {'s1':'ev0','s2':'ev1','s3':'ev2'}
    assert {s['excerpt'] for s in compact['sources']} == {t[-1] for t in texts}


def test_legacy_sources_have_no_invented_recording_context():
    payload = TwinInput(question='谁？', candidates=[dict(memory_item_id='m', statement='原话',
        evidence=[dict(evidence_id='e', excerpt='原话', source_type='CALIBRATION')])])
    compact, _ = compact_twin_materials(payload)
    assert compact['recordings'] == []
    assert 'span_start' not in compact['sources'][0]


@pytest.mark.parametrize('context',[
    {'episode_id':'ep','span_start':1},
    {'episode_id':'ep','span_start':1,'span_end':100},
    {'recorded_at':'2026-09-30T01:00:00Z'},
    {'episode_id':'ep','recorded_at':'2026-09-30T01:00:00'},
])
def test_invalid_context_fails_without_guessing(context):
    with pytest.raises(ValidationError):
        TwinInput(question='谁？', candidates=[dict(memory_item_id='m',statement='原话',
            evidence=[dict(evidence_id='e',excerpt='原话',source_type='SUBJECT',**context)])])
