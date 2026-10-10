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


@pytest.mark.parametrize('failed_call',[1,2])
def test_transient_failure_retried_within_same_three_request_budget(failed_call):
    from app.quoted_twin import QuotedTwin
    from app.errors import ProviderTimeout
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            if self.calls==failed_call:raise ProviderTimeout('temporary')
            if 'selection' not in payload:return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
            return {'reasoning':'Source supports this exact answer','valid':True,'failure_codes':[],'replacement':None},'actual'
    chat=Chat();answer=QuotedTwin(chat).answer(data())
    assert chat.calls==3 and answer.response_type=='ORIGINAL'


def test_exhausted_selection_retries_leave_budget_for_review_but_never_publish():
    from app.quoted_twin import QuotedTwin
    from app.errors import ProviderUnavailable
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1;raise ProviderUnavailable('temporary')
    chat=Chat()
    with pytest.raises(ProviderUnavailable):QuotedTwin(chat).answer(data())
    assert chat.calls==2


def test_transient_retry_does_not_create_a_fourth_semantic_repair_request():
    from app.quoted_twin import QuotedTwin
    from app.errors import ProviderTimeout
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            if self.calls==1:raise ProviderTimeout('temporary')
            p={'points':[{'known':True,'source_ids':['s1']}]}
            if self.calls==2:return p,'actual'
            return {'reasoning':'Attribution still not established','valid':False,'failure_codes':['attribution'],'replacement':p},'actual'
    chat=Chat()
    with pytest.raises(AIOutputInvalid):QuotedTwin(chat).answer(data())
    assert chat.calls==3


def test_authentication_failure_is_never_retried():
    from app.quoted_twin import QuotedTwin
    from app.errors import ProviderAuthenticationFailed
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1;raise ProviderAuthenticationFailed('auth')
    chat=Chat()
    with pytest.raises(ProviderAuthenticationFailed):QuotedTwin(chat).answer(data())
    assert chat.calls==1


def test_malformed_transport_output_is_not_retried():
    from app.quoted_twin import QuotedTwin
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1;raise AIOutputInvalid('Malformed response JSON')
    chat=Chat()
    with pytest.raises(AIOutputInvalid):QuotedTwin(chat).answer(data())
    assert chat.calls==1


def test_no_retry_started_after_total_time_budget(monkeypatch):
    import app.quoted_twin as module
    from app.errors import ProviderTimeout
    now=[0.0];monkeypatch.setattr(module,'monotonic',lambda:now[0])
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1;now[0]=66;raise ProviderTimeout('late timeout')
    chat=Chat()
    with pytest.raises(ProviderTimeout):module.QuotedTwin(chat).answer(data())
    assert chat.calls==1


def test_rate_limit_is_returned_without_immediate_retry():
    from app.quoted_twin import QuotedTwin
    from app.errors import ProviderRateLimited
    class Chat:
        calls=0
        def complete(self,*args):
            self.calls+=1;raise ProviderRateLimited(60)
    chat=Chat()
    with pytest.raises(ProviderRateLimited):QuotedTwin(chat).answer(data())
    assert chat.calls==1


def test_review_receives_selected_material_separately_from_uncited_context():
    from app.quoted_twin import QuotedTwin
    d=data(); other=d.candidates[0].evidence[0].model_copy(deep=True)
    other.evidence_id='unselected';other.excerpt='这是未选入答案的另一件事。'
    other.span_start=100;other.span_end=100+len(other.excerpt)
    d.candidates[0].evidence.append(other)
    class Chat:
        def complete(self,system,payload):
            if 'selection' not in payload:
                return {'points':[{'known':True,'source_ids':['s1']},{'known':False,'source_ids':[]}]},'actual'
            assert payload['cited_material']==[{'known':True,'sources':[{'id':'s1','text':'同事老周告诉我，他父亲曾在铁路工作。','type':'SUBJECT'}]}, {'known':False,'sources':[]}]
            return {'reasoning':'selected quote supports attribution','valid':True,'failure_codes':[],'replacement':None},'actual'
    assert '老周' in QuotedTwin(Chat()).answer(d).answer


def test_quote_failure_has_correlated_stage_metadata_without_private_text(caplog):
    import json
    from app.quoted_twin import QuotedTwin
    class Chat:
        def complete(self,*args):raise AIOutputInvalid('private text and key MUST NOT appear')
    with caplog.at_level('INFO',logger='remember_me.ai_core'):
        with pytest.raises(AIOutputInvalid):QuotedTwin(Chat()).answer(data())
    events=[json.loads(r.message) for r in caplog.records if r.message.startswith('{')]
    result=next(e for e in events if e.get('event')=='quote_request')
    assert result['stage']=='selection' and result['error_type']=='AIOutputInvalid'
    assert result['status']=='failed' and len(result['trace_id'])==32
    assert 'private text' not in str(events) and '同事老周' not in str(events)


def test_selected_context_is_rendered_before_its_later_pronoun():
    from app.quoted_twin import render_ids
    d=data();e=d.candidates[0].evidence[0]
    e.excerpt='车队的老周是我的同事。';e.span_end=len(e.excerpt)
    later=e.model_copy(deep=True);later.evidence_id='later'
    later.excerpt='后来他告诉我，他父亲在铁路工作。'
    later.span_start=100;later.span_end=100+len(later.excerpt)
    d.candidates[0].evidence.append(later)
    answer,_=render_ids({'points':[{'known':True,'source_ids':['s2','s1']}]},d,'actual')
    assert answer.answer.index('车队的老周') < answer.answer.index('后来他')
    assert answer.evidence_ids==['e1','later']


def test_long_unpunctuated_source_has_exact_selectable_windows_and_parent_context():
    from app.quoted_twin import quote_packet,render_ids
    d=data();e=d.candidates[0].evidence[0]
    d.question='休息时为什么把手机静音？'
    e.excerpt='我休息时把手机静音主要是想听完一张唱片不被提示音打断'+('这是后来继续讲述的生活细节'*80)
    e.span_end=len(e.excerpt)
    packet,aliases=quote_packet(d)
    parts=[s for s in packet['recordings'][0]['sources'] if s.get('parent_id')=='s1']
    assert parts and parts[0]['text'].startswith('我休息时把手机静音')
    assert packet['recordings'][0]['sources'][0]['text']==e.excerpt
    for part in parts:
        assert part['text']==e.excerpt[part['start']:part['end']]
        assert len(part['text'])<=140 and aliases[part['id']]=='e1'
    answer,_=render_ids({'points':[{'known':True,'source_ids':[parts[0]['id']]}]},d,'actual')
    assert len(answer.answer)<=500 and answer.evidence_ids==['e1']


def test_long_windows_never_fetch_or_reintroduce_excluded_material():
    from app.quoted_twin import quote_packet
    d=data();e=d.candidates[0].evidence[0]
    e.excerpt='可见有效材料'*90;e.span_start=300;e.span_end=300+len(e.excerpt)
    d.question='有效材料是什么？'
    packet,aliases=quote_packet(d)
    windows=[s for s in packet['recordings'][0]['sources'] if 'parent_id' in s]
    assert windows
    for part in windows:
        assert part['text']==e.excerpt[part['start']:part['end']]
        assert aliases[part['id']]=='e1'


@pytest.mark.parametrize('last_valid',[True,False])
def test_review_schema_can_be_repaired_once_without_bypassing_semantics(last_valid):
    from app.quoted_twin import QuotedTwin
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            if self.calls==1:return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
            if self.calls==2:return {'valid':True},'actual'  # Missing required review fields.
            assert payload['response_schema']['required']
            assert payload['selection']['points'][0]['quotes'][0]['source_id']=='s1'
            return {'reasoning':'Rechecked attribution','valid':last_valid,
                'failure_codes':[] if last_valid else ['attribution'],'replacement':None},'actual'
    chat=Chat()
    if last_valid:assert QuotedTwin(chat).answer(data()).response_type=='ORIGINAL'
    else:
        with pytest.raises(AIOutputInvalid):QuotedTwin(chat).answer(data())
    assert chat.calls==3


def test_malformed_negative_review_cannot_turn_into_a_positive_revote():
    from app.quoted_twin import QuotedTwin
    class Chat:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            if self.calls==1:return {'points':[{'known':True,'source_ids':['s1']}]},'actual'
            if self.calls==2:return {'reasoning':'x'*601,'valid':False,
                'failure_codes':['attribution'],'replacement':None},'actual'
            return {'reasoning':'Another vote','valid':True,'failure_codes':[],'replacement':None},'actual'
    chat=Chat()
    with pytest.raises(AIOutputInvalid):QuotedTwin(chat).answer(data())
    assert chat.calls==2
