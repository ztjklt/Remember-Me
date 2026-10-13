import pytest
from pydantic import ValidationError
from app.chat_summary import ChatSummaryInput, ChatSummaryProvider
from app.twin import TwinInput
from app.grounded_twin import source_packet,validate_answer
from app.errors import AIOutputInvalid

class Chat:
    def __init__(self, value):self.value=value
    def complete(self,system,payload):return self.value,'deepseek-test'

def turn(**kwargs):
    return dict(answer_id='old',question='假如换工作，我可能会考虑上海，但还没有决定。',
        answer='助理建议先比较成本。',response_type='CONVERSATION',**kwargs)

def test_summary_retains_original_quote_and_mechanical_attribution():
    provider=ChatSummaryProvider(Chat({'items':[{'topic':'未决定的假设','answer_id':'old','role':'user',
        'excerpt':'但还没有决定。'}]}))
    result=provider.summarize(ChatSummaryInput(turns=[turn()]))
    assert '本人消息'  in result.summary and '但还没有决定' in result.summary

@pytest.mark.parametrize('item',[
    {'topic':'错误','answer_id':'forged','role':'user','excerpt':'但还没有决定。'},
    {'topic':'错误','answer_id':'old','role':'user','excerpt':'我已决定搬去上海'},
    {'topic':'错误','answer_id':'old','role':'user','excerpt':'助理建议先比较成本。'},
    {'topic':'错误','answer_id':'old','role':'system','excerpt':'但还没有决定。'}])
def test_summary_rejects_wrong_sources(item):
    with pytest.raises(AIOutputInvalid):ChatSummaryProvider(Chat({'items':[item]})).summarize(ChatSummaryInput(turns=[turn()]))

def test_historical_sources_have_time_and_never_become_person_evidence():
    payload=TwinInput(question='我以前决定了吗？',candidates=[],conversation_mode=True,
        conversation_recall=[turn(created_at='2026-10-01T00:00:00+00:00')],conversation_summary='只做导航的摘要')
    packet,aliases=source_packet(payload)
    assert packet['conversation'][0]['historical_recall']
    assert packet['conversation'][0]['created_at'].startswith('2026-10-01')
    assert packet['chat_summary_hint']=='只做导航的摘要' and not aliases
    raw={'points':[{'question_part':'回顾','mode':'CONVERSATION','text':'你之前说还没有决定。','source_ids':['c1'],'names':[]}]}
    assert validate_answer(raw,payload,'test').response_type=='CONVERSATION'
    raw['points'][0]['mode']='SIMULATION'
    with pytest.raises(AIOutputInvalid):validate_answer(raw,payload,'test')

def test_stale_assistant_excluded_and_client_budget_strict():
    with pytest.raises(ValidationError):TwinInput(question='q',candidates=[],conversation_recall=[turn()])
    payload=TwinInput(question='q',candidates=[],conversation_mode=True,
        conversation_recall=[{**turn(),'answer':None,'assistant_stale':True}])
    packet,_=source_packet(payload)
    assert not any(t['role']=='assistant' for t in packet['conversation'])
