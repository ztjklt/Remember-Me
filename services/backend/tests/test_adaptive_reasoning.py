from datetime import datetime, timedelta, timezone
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select
from app.capture_policy import burden, entropy, evaluate, information_gain, learn
from app.capture_planner import plan
from app.models import CaptureQuestion, Episode, Evidence, MemoryItem, utcnow
from app.temporal_reasoning import graph, interval, paths, presentation
from test_full_agent_loop import SemanticProposals, capture, own_data
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def test_information_gain_is_mutual_information_not_fixed_priority():
    assert information_gain(.5, .5) == 0
    assert 0 < information_gain(.5, .75) < entropy(.5)
    assert information_gain(.95, .75) < information_gain(.5, .75)
    low = {('PREFERENCES', 'contradiction'): {'success': 1., 'failure': 20., 'trials': 20., 'minutes': 8.}}
    poor = evaluate('PREFERENCES', 'contradiction', [], [], low, {'fatigue':0}, NOW)
    fresh = evaluate('IDENTITY', 'missing_domain', [], [], low, {'fatigue':0}, NOW)
    assert poor['score'] < fresh['score'] and poor['information_gain_bits'] == 0


def test_burden_stops_and_recovers_without_read_count():
    events = [NS(created_at=NOW-timedelta(minutes=i), duration_ms=60000, capture_metadata={'question_id':str(i)},
                 transcript_reviewed_at=None, transcript='') for i in range(4)]
    assert burden(events,NOW)['paused']
    assert not burden(events,NOW+timedelta(hours=2))['paused']
    assert burden(events[:2],NOW)['budget']==1
    assert burden(events[:2],NOW)==burden(events[:2],NOW)


def test_explicit_pause_needs_confirmation_and_cannot_be_quoted_history():
    e=NS(created_at=NOW,duration_ms=1000,capture_metadata={},transcript_reviewed_at=NOW,transcript='我想休息一下。')
    assert burden([e],NOW)['reason']=='explicit_pause'
    e.transcript='去年我说我想休息一下，现在愿意回答。'
    assert not burden([e],NOW)['paused']
    e.transcript='我想休息一下'; e.transcript_reviewed_at=None
    assert not burden([e],NOW)['paused']


def test_long_term_reward_decays_and_deleted_source_cannot_reward():
    q=NS(question_id='q',target_domain='IDENTITY',reason='missing_domain',status='answered',policy_snapshot={'baseline':{'statements':[],'memory_ids':[],'unresolved':0}})
    ep=NS(episode_id='e',created_at=NOW-timedelta(days=30),duration_ms=120000,capture_metadata={'question_id':'q'})
    m=NS(episode_id='e',memory_item_id='m',content='本人姓名')
    t=NS(domain='IDENTITY',status='active',memory_item_ids=['m'])
    stats=learn([q],[ep],[m],[t],NOW)
    assert stats[('IDENTITY','missing_domain')]['success']==3.5
    assert stats[('IDENTITY','missing_domain')]['trials']==.5
    assert learn([q],[ep],[],[t],NOW)=={}


def test_refresh_and_rest_preserve_pending_ids(app,client,session):
    own,headers=own_data(session); app.state.ai_client=SemanticProposals()
    capture(client,app,own,headers,'base','我喜欢咖啡。')
    base=f'/api/v1/subjects/{own.subject_id}'
    first=client.get(base+'/questions',headers=headers).json()['items']
    assert first==client.get(base+'/questions',headers=headers).json()['items']
    session.expire_all()
    pending=list(session.scalars(select(CaptureQuestion).where(CaptureQuestion.subject_id==own.subject_id)))
    assert len(pending)==len(first)
    assert all(q.policy_snapshot['information_gain_bits']>0 for q in pending)
    ep=session.scalar(select(Episode).where(Episode.subject_id==own.subject_id))
    ep.transcript='先暂停提问'; ep.transcript_reviewed_at=utcnow(); ep.created_at=utcnow(); session.commit()
    assert client.get(base+'/questions',headers=headers).json()['items']==[]
    session.expire_all()
    assert all(q.status=='pending' for q in pending)
    assert plan(session,own.subject_id,now=utcnow()+timedelta(hours=2))


def setup_chain(app,client,session):
    own,headers=own_data(session); app.state.ai_client=SemanticProposals(); ids=[]
    for key,text in [('a','2020年1月1日我搬家。'),('b','2021年1月1日我换工作，因为搬家所以换工作。'),('c','2022年1月1日我开始散步，因为换工作所以开始散步。')]:
        eid=capture(client,app,own,headers,key,text); session.expire_all()
        ids.append(session.scalar(select(MemoryItem).where(MemoryItem.episode_id==eid)).memory_item_id)
    def anchor(i,phrase,time):
        m=session.get(MemoryItem,ids[i])
        return {'memory_item_id':m.memory_item_id,'content':m.content,'evidence_ids':m.evidence_ids,'quote':phrase,'time_text':time}
    a=anchor(0,'我搬家','2020年1月1日'); b=anchor(1,'我换工作','2021年1月1日'); c=anchor(2,'我开始散步','2022年1月1日')
    for i,left,right in [(1,a,b),(2,b,c)]:
        m=session.get(MemoryItem,ids[i]); e=session.get(Evidence,m.evidence_ids[0])
        m.item_metadata={**m.item_metadata,'temporal_causal':[{'version':'temporal-causal-v1','input_statement':m.content,'cause':left,'effect':right,'relation':'REPORTED_CAUSE','quote':e.excerpt,'context':None,'evidence_ids':m.evidence_ids,'model_version':'test-causal'}]}
    session.commit(); return own,headers,ids


def test_multi_hop_paths_carry_complete_evidence_and_real_event_time(app,client,session):
    own,headers,ids=setup_chain(app,client,session); model=graph(session,own.subject_id)
    assert len(model['edges'])==2
    targets={n['id'] for n in model['nodes'].values() if n['memory_item_id']==ids[2]}
    chain=next(p for p in paths(model,targets) if len(p['edges'])==2)
    assert chain['kind']=='INFERRED_REPORTED_CHAIN' and len(chain['evidence_ids'])==3
    assert model['nodes'][chain['nodes'][0]]['event_time']['start'].startswith('2020-01-01')
    assert interval('去年') is None and interval('2020年')['precision']=='year'
    assert interval('2020年2月')['end'].startswith('2020-03-01') and interval('2020-02-30') is None
    assert presentation(model,ids[2])[0]['status']=='supported'


def test_source_correction_and_deletion_retract_paths(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    session.get(MemoryItem,ids[0]).content='本人纠正了搬家的经历'; session.commit()
    model=graph(session,own.subject_id)
    assert len(model['edges'])==1
    assert not any(len(p['edges'])>1 for p in paths(model,set(model['nodes'])))
    session.get(MemoryItem,ids[1]).deleted_at=utcnow(); session.commit()
    assert graph(session,own.subject_id)['edges']==[]


@pytest.mark.parametrize('relation',['BEFORE','ASSOCIATED_WITH','HYPOTHESIS'])
def test_noncausal_relations_never_become_causal_paths(app,client,session,relation):
    own,headers,ids=setup_chain(app,client,session)
    for mid in ids[1:]:
        m=session.get(MemoryItem,mid); meta=deepcopy(m.item_metadata); meta['temporal_causal'][0]['relation']=relation; m.item_metadata=meta
    session.commit(); model=graph(session,own.subject_id)
    assert paths(model,set(model['nodes']))==[]


def test_reversed_time_and_unquoted_context_are_rejected(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    m=session.get(MemoryItem,ids[1]); meta=deepcopy(m.item_metadata); edge=meta['temporal_causal'][0]
    edge['cause'],edge['effect']=edge['effect'],edge['cause']; m.item_metadata=meta; session.commit()
    model=graph(session,own.subject_id)
    assert any('reversed_time' in e['issues'] and e['status']=='contested' for e in model['edges'])
    for mid in ids[1:]:
        m=session.get(MemoryItem,mid); meta=deepcopy(m.item_metadata); meta['temporal_causal'][0]['context']='不在原文的场景'; m.item_metadata=meta
    session.commit(); assert graph(session,own.subject_id)['edges']==[]


def test_third_party_and_other_subjects_cannot_supply_anchors(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    m=session.get(MemoryItem,ids[0]); session.get(Evidence,m.evidence_ids[0]).source_type='THIRD_PARTY'; session.commit()
    assert len(graph(session,own.subject_id)['edges'])==1 and graph(session,'other')['edges']==[]


def test_knowledge_cutoff_does_not_know_later_recording(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    assert graph(session,own.subject_id,as_of=datetime(2019,1,1,tzinfo=timezone.utc))['edges']==[]


def test_twin_receives_chain_and_refuses_unproved_counterfactual(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    from test_twin_voice import TinyEncoder
    app.state.settings.ai_backend='http'; app.state.embedding_encoder=TinyEncoder()
    class ReasonTwin:
        seen=None
        def answer(self,question,candidates):
            self.seen=candidates
            return {'answer':'搬家之后换工作，继而开始散步。','response_type':'SIMULATION','evidence_ids':sorted({e['evidence_id'] for c in candidates for e in c['evidence']}),'confidence':.9,'model_version':'test-causal'}
    provider=ReasonTwin(); app.state.twin_client=provider; base=f'/api/v1/subjects/{own.subject_id}'
    cloud=client.post('/api/v1/consents',headers=headers,json={'subject_id':own.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    answer=client.post(base+'/twin/answers',headers=headers,json={'question':'为什么开始散步？','cloud_consent_id':cloud})
    assert answer.status_code==200,answer.text
    assert answer.json()['response_type']=='SIMULATION' and answer.json()['confidence']<=.65
    assert any('归因链' in note for c in provider.seen for note in c['graph_facts'])
    answer=client.post(base+'/twin/answers',headers=headers,json={'question':'如果没有搬家会开始散步吗？','cloud_consent_id':cloud})
    assert answer.json()['response_type']=='UNKNOWN'


def test_denial_in_same_context_blocks_chain_and_generates_clarification(app,client,session):
    from app.temporal_reasoning import clarification_questions
    own,headers,ids=setup_chain(app,client,session)
    eid=capture(client,app,own,headers,'denial','搬家不是原因，换工作与搬家无关。')
    session.expire_all(); m=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==eid))
    old=session.get(MemoryItem,ids[1]).item_metadata['temporal_causal'][0]
    denied={**deepcopy(old),'input_statement':m.content,'relation':'DENIES_CAUSE','quote':m.content,'evidence_ids':m.evidence_ids}
    m.item_metadata={**m.item_metadata,'temporal_causal':[denied]}; session.commit()
    model=graph(session,own.subject_id)
    assert any('counter_evidence' in e['issues'] for e in model['edges'])
    assert list(clarification_questions(model))
    target={n['id'] for n in model['nodes'].values() if n['memory_item_id']==ids[2]}
    assert not any(len(p['edges'])==2 for p in paths(model,target))


def test_cycles_without_dates_are_not_used_for_inference(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    for mid in ids[1:]:
        m=session.get(MemoryItem,mid); meta=deepcopy(m.item_metadata)
        for node in ('cause','effect'): meta['temporal_causal'][0][node]['time_text']=None
        m.item_metadata=meta
    # Opposite direction recorded in another subjective attribution.
    m=session.get(MemoryItem,ids[2]); meta=deepcopy(m.item_metadata)
    opposite=deepcopy(session.get(MemoryItem,ids[1]).item_metadata['temporal_causal'][0])
    opposite['cause'],opposite['effect']=opposite['effect'],opposite['cause']
    opposite.update(input_statement=m.content,quote=m.content,evidence_ids=m.evidence_ids)
    meta['temporal_causal'].append(opposite); m.item_metadata=meta; session.commit()
    model=graph(session,own.subject_id)
    assert sum('cycle' in e['issues'] for e in model['edges'])==2


def test_different_explicit_contexts_do_not_form_a_multihop_chain(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    for mid,context in [(ids[1],'换工作'),(ids[2],'开始散步')]:
        m=session.get(MemoryItem,mid); meta=deepcopy(m.item_metadata)
        meta['temporal_causal'][0]['context']=context; m.item_metadata=meta
    session.commit(); model=graph(session,own.subject_id)
    assert len(model['edges'])==2
    assert not any(len(p['edges'])>1 for p in paths(model,set(model['nodes'])))


def test_uncertain_intervals_do_not_create_false_precise_order():
    from app.temporal_reasoning import time_relation
    assert time_relation(interval('2020年'), interval('2020年2月'))=='OVERLAPS'
    assert time_relation(interval('2020年1月1日'), interval('2020年2月'))=='BEFORE'
    assert time_relation(None, interval('2020年2月'))=='UNKNOWN'
    assert time_relation(interval('2021年'), interval('2020年'))=='AFTER'


def test_event_quote_framing_reuses_node_without_merging_distinct_events(app,client,session):
    own,headers,ids=setup_chain(app,client,session)
    middle=session.get(MemoryItem,ids[1]); middle.memory_type='EVENT'
    middle.content='2021年1月1日换工作'
    middle_meta=deepcopy(middle.item_metadata)
    middle_meta['temporal_causal'][0]['input_statement']=middle.content
    middle_meta['temporal_causal'][0]['effect']['content']=middle.content
    middle.item_metadata=middle_meta
    m=session.get(MemoryItem,ids[2]); meta=deepcopy(m.item_metadata)
    meta['temporal_causal'][0]['cause']['quote']='换工作'
    meta['temporal_causal'][0]['cause']['content']=middle.content
    meta['temporal_causal'][0]['cause']['time_text']=None
    m.item_metadata=meta; session.commit()
    model=graph(session,own.subject_id)
    assert any(len(p['edges'])==2 for p in paths(model,set(model['nodes'])))
    from app.temporal_reasoning import event_key
    assert event_key('2021年1月1日我换工作。')==event_key('换工作')
    assert event_key('我没换工作')!=event_key('换工作')
