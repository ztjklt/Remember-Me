import json
from app.twin import TwinInput
from app.quoted_twin import quote_packet
from test_grounded_twin import data


def test_compaction_round_trip_preserves_every_source_condition_and_negation():
    from app.voice_packet import compact_packet,expand_packet
    payload=data();packet,_=quote_packet(payload)
    packet['recordings'][0]['sources'].append({'id':'s99','text':'过去喜欢浓茶，但后来只喝淡茶；不是因为生病。',
        'type':'SUBJECT','temporal_context':'1986暂记已被1987更正；月份未知。','parent_id':'s1','start':0,'end':28})
    packet['confirmed_understanding'].append({'text':'节俭，但给孩子画笔是例外。','source_ids':['s1','s99']})
    compact=compact_packet(packet)
    assert expand_packet(compact)==packet
    assert '不是因为生病' in json.dumps(compact,ensure_ascii=False)
    assert '月份未知' in json.dumps(compact,ensure_ascii=False)
    assert '画笔是例外' in json.dumps(compact,ensure_ascii=False)


def test_compaction_reduces_repeated_structure_without_mutation():
    from app.voice_packet import compact_packet,expand_packet
    packet={'question':'后来呢？','recordings':[{'episode_id':'ep1','recorded_at':'2026-01-01',
        'sources':[{'id':f's{i}','type':'SUBJECT','text':f'第{i}件事，后来没有去。','temporal_context':'本人更正年份，日期仍未知。'} for i in range(20)]}],
        'confirmed_understanding':[{'text':'一个有条件的理解','source_ids':['s1']}]}
    before=json.dumps(packet,ensure_ascii=False)
    compact=compact_packet(packet)
    assert len(json.dumps(compact,ensure_ascii=False))<len(before)*.8
    assert json.dumps(packet,ensure_ascii=False)==before
    assert expand_packet(compact)==packet
