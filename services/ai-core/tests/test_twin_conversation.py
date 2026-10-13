import pytest
from pydantic import ValidationError
from app.twin import TwinInput
from app.grounded_twin import GroundedTwin, source_packet, validate_answer
from app.errors import AIOutputInvalid


def payload():
    return TwinInput(question='那我刚才说喜欢什么？', candidates=[], conversation_mode=True,
        conversation_turns=[dict(answer_id='ta_1',question='我喜欢安静的地方。',
            answer='你刚才提到喜欢安静的地方。',response_type='CONVERSATION',assistant_stale=False)])


def answer():
    return {'points':[{'question_part':'回顾对话','mode':'CONVERSATION',
        'text':'你刚才说喜欢安静的地方。','source_ids':['c1'],'names':[]}]}


def test_exact_history_and_current_message_are_distinct_from_person_evidence():
    packet,aliases=source_packet(payload())
    assert aliases=={} and packet['recordings']==[]
    assert packet['conversation'][0]['role']=='user'
    assert packet['conversation'][0]['text']=='我喜欢安静的地方。'
    assert packet['conversation'][1]['is_person_evidence'] is False
    assert packet['conversation'][-1]['current'] is True
    output=validate_answer(answer(),payload(),'test-model')
    assert output.response_type=='CONVERSATION' and output.evidence_ids==[] and output.confidence==0


def test_history_cannot_be_promoted_to_original_or_person_simulation():
    for kind in ['ORIGINAL','SIMULATION']:
        raw=answer();raw['points'][0]['mode']=kind
        with pytest.raises(AIOutputInvalid): validate_answer(raw,payload(),'test')
    legacy=TwinInput(question='你好',candidates=[])
    with pytest.raises(AIOutputInvalid): validate_answer(answer(),legacy,'test')


def test_stale_assistant_and_oversized_history_are_refused():
    with pytest.raises(ValidationError):
        TwinInput(question='继续',candidates=[],conversation_mode=True,conversation_turns=[
            dict(answer_id='ta',question='问题',answer='过期内容',response_type='SIMULATION',assistant_stale=True)])
    many=[dict(answer_id=str(i),question='问'*1000,answer='答'*500,response_type='CONVERSATION') for i in range(20)]
    with pytest.raises(ValidationError): TwinInput(question='继续',candidates=[],conversation_mode=True,conversation_turns=many)


def test_no_recordings_still_uses_draft_and_semantic_review():
    class Chat:
        def __init__(self):self.calls=[]
        def complete(self,system,packet):
            self.calls.append((system,packet))
            if 'points' not in packet: return answer(),'actual-model'
            return {'checks':[dict(point=1,supported=True,complete=True,attribution=True,
                                  time_consistent=True,mode_correct=True,unsupported_claims=[])]},'actual-model'
    chat=Chat();out=GroundedTwin(chat).answer(payload())
    assert out.response_type=='CONVERSATION' and len(chat.calls)==2
    assert 'conversation-v2' in chat.calls[0][0]
    assert 'twin-points-v7。' not in chat.calls[0][0]
    assert 'conversation-v2-review' in chat.calls[1][0]
    assert chat.calls[1][1]['cited_material'][0]['sources'][0]['role']=='user'
    assert chat.calls[1][1]['rendered_answer']['answer']==out.answer


def test_semantic_rejection_is_failure_not_fabricated_unknown():
    class Chat:
        def complete(self,system,packet):
            if 'points' not in packet: return answer(),'actual'
            return {'checks':[dict(point=1,supported=False,complete=True,attribution=False,
                                  time_consistent=True,mode_correct=True,unsupported_claims=['promoted a question to fact'])]},'actual'
    with pytest.raises(AIOutputInvalid,match='review'): GroundedTwin(Chat()).answer(payload())


def test_confirmed_expression_examples_are_style_only_not_source_ids():
    p=payload();p.expression_examples=['先看看情况吧。']
    packet,aliases=source_packet(p)
    assert packet['confirmed_expression_examples']==['先看看情况吧。']
    assert aliases=={}
