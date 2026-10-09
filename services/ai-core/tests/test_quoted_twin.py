import pytest
from app.errors import AIOutputInvalid
from test_grounded_twin import data

def plan(quote='同事老周告诉我，他父亲曾在铁路工作。',source='s1'):
    return {'points':[{'known':True,'quotes':[{'source_id':source,'text':quote}]}, {'known':False,'quotes':[]}]}

def test_exact_quote_is_not_rewritten_into_a_new_person_claim():
    from app.quoted_twin import render
    answer,_=render(plan(),data(),'actual')
    assert '同事老周告诉我，他父亲曾在铁路工作。' in answer.answer
    assert '老周以前在铁路工作' not in answer.answer
    assert answer.response_type=='SIMULATION' and '部分问题尚无明确材料' in answer.answer

@pytest.mark.parametrize('quote,source',[('老周以前在铁路工作。','s1'),('同事老周告诉我，他父亲曾在铁路工作。','s99'),('老周说他父亲在铁路工作','s1')])
def test_modified_or_incomplete_quote_refused(quote,source):
    from app.quoted_twin import render
    with pytest.raises(AIOutputInvalid):render(plan(quote,source),data(),'actual')

def test_full_original_and_written_source_have_different_labels():
    from app.quoted_twin import render
    p=plan();p['points']=p['points'][:1]
    assert render(p,data(),'actual')[0].response_type=='ORIGINAL'
    d=data();d.candidates[0].evidence[0].source_type='CALIBRATION'
    answer,_=render(p,d,'actual')
    assert answer.response_type=='SIMULATION' and '本人书面说明' in answer.answer

def test_unknown_cannot_smuggle_a_quote_and_known_cannot_have_no_source():
    from app.quoted_twin import render
    for p in [{'points':[{'known':False,'quotes':[{'source_id':'s1','text':'x'}]}]}, {'points':[{'known':True,'quotes':[]}]}]:
        with pytest.raises(AIOutputInvalid):render(p,data(),'actual')

def test_copied_but_irrelevant_quote_still_requires_review():
    from app.quoted_twin import QuotedTwin
    class Chat:
        def complete(self,system,payload):
            if 'selection' not in payload:return {'points':[{'known':True,'source_ids':['s1']},{'known':False,'source_ids':[]}]},'actual'
            assert payload['rendered_answer'] and payload['selection']['points'][0]['quotes']
            return {'reasoning':'Test finding with referenced material','valid':False,'failure_codes':['irrelevant'],'replacement':None},'actual'
    with pytest.raises(AIOutputInvalid,match='relevance'):QuotedTwin(Chat()).answer(data())

def test_one_review_correction_is_rechecked_without_adding_a_fourth_call():
    from app.quoted_twin import QuotedTwin
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            p={'points':[{'known':True,'source_ids':['s1']},{'known':False,'source_ids':[]}]}
            if self.calls==1:return {'points':[{'known':False,'source_ids':[]}]},'actual'
            if self.calls==2:return {'reasoning':'Test finding with referenced material','valid':False,'failure_codes':['missing_known'],'replacement':p},'actual'
            assert payload['selection']['points'][0]['known'] is True
            return {'reasoning':'Test supported quote','valid':True,'failure_codes':[],'replacement':None},'actual'
    chat=Chat();answer=QuotedTwin(chat).answer(data())
    assert chat.calls==3 and '老周' in answer.answer and answer.evidence_ids==['e1']

def test_failed_repair_review_never_publishes_or_retries_again():
    from app.quoted_twin import QuotedTwin
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1;p={'points':[{'known':True,'source_ids':['s1']}]}
            if self.calls==1:return p,'actual'
            return {'reasoning':'Test finding with referenced material','valid':False,'failure_codes':['attribution'],'replacement':p},'actual'
    chat=Chat()
    with pytest.raises(AIOutputInvalid):QuotedTwin(chat).answer(data())
    assert chat.calls==3


def test_id_selection_copies_without_model_spelling_or_punctuation():
    from app.quoted_twin import render_ids
    p={'points':[{'known':True,'source_ids':['s1']}]}
    answer,selection=render_ids(p,data(),'actual')
    assert answer.response_type=='ORIGINAL'
    assert answer.answer==data().candidates[0].evidence[0].excerpt
    assert selection.points[0].quotes[0].text==answer.answer
    p['points'][0]['source_ids']=['s2']
    with pytest.raises(AIOutputInvalid):render_ids(p,data(),'actual')


def test_quote_packet_prefers_whole_authorized_sentence_over_contained_fragment():
    from app.quoted_twin import quote_packet,render_ids
    from app.twin import TwinEvidence
    d=data();e=d.candidates[0].evidence[0]
    e.excerpt='搬家能解决所有困难';e.span_start=4;e.span_end=4+len(e.excerpt)
    full='我没有说搬家能解决所有困难。'
    d.candidates[0].evidence.append(TwinEvidence(evidence_id='whole',excerpt=full,source_type='SUBJECT',
        episode_id=e.episode_id,recorded_at=e.recorded_at,span_start=0,span_end=len(full)))
    packet,aliases=quote_packet(d)
    texts=[s['text'] for r in packet['recordings'] for s in r['sources']]
    assert texts==[full]
    with pytest.raises(AIOutputInvalid):render_ids({'points':[{'known':True,'source_ids':['s1']}]},d,'actual')
    assert render_ids({'points':[{'known':True,'source_ids':['s2']}]},d,'actual')[0].answer==full


def test_quote_packet_does_not_merge_different_recordings_or_temporal_context():
    from app.quoted_twin import quote_packet
    d=data();other=d.candidates[0].model_copy(deep=True)
    other.evidence[0].evidence_id='other';other.evidence[0].episode_id='different'
    d.candidates.append(other)
    packet,_=quote_packet(d);assert len(packet['recordings'])==2
    other.evidence[0].episode_id='ep1';other.evidence[0].temporal_context='历史记载，后来发生变化'
    packet,_=quote_packet(d);assert len(packet['recordings'][0]['sources'])==2
