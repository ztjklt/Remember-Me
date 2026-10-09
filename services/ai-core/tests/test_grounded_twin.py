import copy
import pytest
from app.twin import TwinInput
from app.errors import AIOutputInvalid


def data():
    return TwinInput(question='谁讲过父亲的工作，母亲在哪里工作？', candidates=[
        dict(memory_item_id='m1',statement='未经证实的摘要姓名',evidence=[dict(evidence_id='e1',
             excerpt='同事老周告诉我，他父亲曾在铁路工作。',source_type='SUBJECT',
             episode_id='ep1', recorded_at='2026-09-30T02:00:00Z',span_start=0,span_end=len('同事老周告诉我，他父亲曾在铁路工作。'))])])


def raw():
    return dict(points=[dict(question_part='父亲的工作',mode='SIMULATION',text='据讲述者转述，同事老周说其父亲曾在铁路工作。',
        source_ids=['s1'],names=[dict(text='老周',source_id='s1')]),
        dict(question_part='母亲的工作',mode='UNKNOWN',text='未留下相关材料。',source_ids=[],names=[])])


def test_grouped_packet_does_not_promote_unreviewed_summary_to_fact():
    from app.grounded_twin import source_packet
    packet,aliases=source_packet(data())
    assert packet['recordings'][0]['sources'][0]['text']=='同事老周告诉我，他父亲曾在铁路工作。'
    assert '未经证实' not in str(packet)
    assert aliases['s1']=='e1'


def test_partial_unknown_is_rendered_without_discarding_known_answer():
    from app.grounded_twin import validate_answer
    output=validate_answer(raw(), data(), 'actual')
    assert output.response_type=='SIMULATION'
    assert output.evidence_ids==['e1']
    assert '据讲述者转述' in output.answer and '母亲的工作：未留下相关材料。' in output.answer


@pytest.mark.parametrize('mutation',['unknown_id','unsupported_name','source_missing','global_unknown'])
def test_invalid_points_cannot_be_published(mutation):
    from app.grounded_twin import validate_answer
    value=copy.deepcopy(raw());point=value['points'][0]
    if mutation=='unknown_id':point['source_ids']=['fake']
    if mutation=='unsupported_name':point['names'][0]['text']='周先生'
    if mutation=='source_missing':point['source_ids']=[]
    if mutation=='global_unknown':point['text']='现有记录还不足以确定。但他父亲在铁路工作。'
    with pytest.raises(AIOutputInvalid):validate_answer(value,data(),'actual')


def test_original_still_copies_real_text_and_never_written_supplement():
    from app.grounded_twin import validate_answer
    value=dict(points=[dict(question_part='原话',mode='ORIGINAL',text='',source_ids=['s1'],names=[])])
    output=validate_answer(value,data(),'actual')
    assert output.response_type=='ORIGINAL' and output.answer==data().candidates[0].evidence[0].excerpt
    changed=data();changed.candidates[0].evidence[0].source_type='CALIBRATION'
    with pytest.raises(AIOutputInvalid):validate_answer(value,changed,'actual')


def test_review_requires_every_point_and_false_is_error_not_unknown():
    from app.grounded_twin import GroundedTwin
    class Chat:
        def complete(self,system,payload):
            if 'points' not in payload:return raw(),'actual'
            return {'checks':[{'point':1,'supported':True,'complete':True,'attribution':True,'time_consistent':True,'mode_correct':True},
                              {'point':2,'supported':False,'complete':True,'attribution':True,'time_consistent':True,'mode_correct':True}]},'actual'
    with pytest.raises(AIOutputInvalid,match='review'):GroundedTwin(Chat()).answer(data())


@pytest.mark.parametrize('checks', [[],[1],[2,1],[1,1]])
def test_review_cannot_omit_or_duplicate_questions(checks):
    from app.grounded_twin import GroundedTwin
    class Chat:
        def complete(self,system,payload):
            if 'points' not in payload:return raw(),'actual'
            return {'checks':[dict(point=n,supported=True,complete=True,attribution=True,time_consistent=True,mode_correct=True) for n in checks]},'actual'
    with pytest.raises(AIOutputInvalid):GroundedTwin(Chat()).answer(data())


def test_original_selection_is_also_reviewed_for_answer_relevance():
    from app.grounded_twin import GroundedTwin
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            if self.calls==1:return dict(points=[dict(question_part='原话',mode='ORIGINAL',text='',source_ids=['s1'],names=[])]),'actual'
            return {'checks':[dict(point=1,supported=True,complete=False,attribution=True,time_consistent=True,mode_correct=True)]},'actual'
    chat=Chat()
    with pytest.raises(AIOutputInvalid):GroundedTwin(chat).answer(data())
    assert chat.calls==2


def test_conflicting_metadata_for_same_source_id_is_rejected():
    from app.grounded_twin import source_packet
    value=data();second=value.candidates[0].model_copy(deep=True)
    second.evidence[0].excerpt='同样编号的另一份文字'
    value.candidates.append(second)
    with pytest.raises(AIOutputInvalid):source_packet(value)


def test_full_packet_keeps_calibration_and_temporal_revisions():
    from app.grounded_twin import source_packet
    value=data();e=value.candidates[0].evidence[0]
    e.source_type='CALIBRATION';e.span_start=e.span_end=None;e.temporal_context='历史记载，后来已变化'
    packet,_=source_packet(value);source=packet['recordings'][0]['sources'][0]
    assert source['type']=='CALIBRATION' and source['temporal_context']=='历史记载，后来已变化'
    assert source['text']==e.excerpt


@pytest.mark.parametrize('text,valid',[
    ('结束后我给妈妈打了电话。',False),
    ('我喜欢散步。',False),
    ('据讲述者说，他提到“我喜欢散步”。',True),
    ('据讲述者说，这是当时的自我理解。',True),
])
def test_generated_answer_cannot_speak_as_the_subject(text,valid):
    from app.grounded_twin import validate_answer
    value=raw();value['points']=value['points'][:1];value['points'][0].update(text=text,names=[])
    if valid:assert validate_answer(value,data(),'actual').response_type=='SIMULATION'
    else:
        with pytest.raises(AIOutputInvalid,match='first person'):validate_answer(value,data(),'actual')


def test_original_model_text_cannot_differ_from_what_will_be_reviewed():
    from app.grounded_twin import validate_answer
    value=dict(points=[dict(question_part='原话',mode='ORIGINAL',text='模型另外编写的文字',source_ids=['s1'],names=[])])
    with pytest.raises(AIOutputInvalid,match='Original text must be empty'):
        validate_answer(value,data(),'actual')


def test_review_receives_materialized_original_and_final_visible_answer():
    from app.grounded_twin import GroundedTwin
    class Chat:
        def complete(self,system,payload):
            if 'points' not in payload:
                return dict(points=[dict(question_part='原话',mode='ORIGINAL',text='',source_ids=['s1'],names=[])]),'actual'
            assert payload['points'][0]['text']==data().candidates[0].evidence[0].excerpt
            assert payload['rendered_answer']['answer']==payload['points'][0]['text']
            assert payload['rendered_answer']['response_type']=='ORIGINAL'
            return {'checks':[dict(point=1,supported=True,complete=True,attribution=True,time_consistent=True,mode_correct=True)]},'actual'
    assert GroundedTwin(Chat()).answer(data()).response_type=='ORIGINAL'


def test_original_in_mixed_generated_response_remains_explicitly_quoted():
    from app.grounded_twin import validate_answer
    value=raw();value['points'][0].update(mode='ORIGINAL',text='',names=[])
    output=validate_answer(value,data(),'actual')
    assert output.response_type=='SIMULATION'
    assert '本人原话：“同事老周告诉我，他父亲曾在铁路工作。”' in output.answer
    assert '母亲的工作：未留下相关材料。' in output.answer


def test_evidence_about_an_unanswered_question_is_not_a_known_answer():
    from app.grounded_twin import GroundedTwin
    class Chat:
        def complete(self,system,payload):
            if 'points' not in payload:return raw(),'actual'
            return {'checks':[dict(point=n,supported=True,complete=True,attribution=True,time_consistent=True,mode_correct=False if n==1 else True) for n in [1,2]]},'actual'
    with pytest.raises(AIOutputInvalid,match='failed evidence review'):GroundedTwin(Chat()).answer(data())
