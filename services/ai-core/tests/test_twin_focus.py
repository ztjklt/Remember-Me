from app.providers.weixin import compact_twin_materials
from app.twin import TwinInput


def payload(text, question='旅行目的地和日期定了吗？', source='SUBJECT'):
    return TwinInput(question=question,candidates=[dict(memory_item_id='m1',statement=text,
        evidence=[dict(evidence_id='real-source',excerpt=text,source_type=source)])])


def test_focus_keeps_negative_context_and_exact_source_offsets():
    text='我回忆过去修车的事情。'*60+'旅行目的地还没有确定。日期也没有定，不能说已经订票。'+'以前工作的故事。'*60
    data=payload(text); original=data.model_dump()
    compact,aliases=compact_twin_materials(data)
    hints=compact['focus_passages']
    assert any('目的地还没有确定' in h['excerpt'] and '日期也没有定' in h['excerpt'] for h in hints)
    assert all(h['excerpt']==text[h['start']:h['end']] for h in hints)
    assert all(aliases[h['evidence_id']]=='real-source' for h in hints)
    assert compact['sources'][0]['excerpt']==text and data.model_dump()==original


def test_focus_keeps_third_party_attribution_and_does_not_invent_a_name():
    text='他不是我的同事。李清是我的客户，他告诉我父亲喜欢游泳。我自己不喜欢游泳。'
    compact,_=compact_twin_materials(payload(text,'李青的父亲喜欢什么？','THIRD_PARTY'))
    hints=compact['focus_passages']
    assert hints and all(h['source_type']=='THIRD_PARTY' for h in hints)
    assert any('他告诉我父亲' in h['excerpt'] for h in hints)
    assert all('李青' not in h['excerpt'] for h in hints)
def test_unproven_focus_protocol_is_not_default():
    from app.providers.weixin import WeixinTwinProvider
    from app.twin import TwinInput
    payload=TwinInput.model_validate({'question':'还有什么记录？','candidates':[
        {'memory_item_id':'m','statement':'没有其他记录。','evidence':[{'evidence_id':'e','excerpt':'没有其他记录。','source_type':'SUBJECT'}]}]})
    provider=WeixinTwinProvider(api_key='test')
    observed={}
    def complete(system,data):
        observed.update(system=system,data=data)
        return {'answer':'现有记录还不足以确定。','response_type':'UNKNOWN','evidence_ids':[],'confidence':0},'test'
    provider.complete=complete
    try: provider.answer(payload)
    finally: provider.close()
    assert 'focus_passages' not in observed['data']
    assert 'twin-context-v8' in observed['system']
