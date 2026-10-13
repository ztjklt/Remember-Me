"""Product behavior tests. Synthetic fixtures are not live model acceptance."""
from app.materials import effective_materials
from app.models import Episode
from test_agent_workbench import setup_pair


def prepare(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    sources = effective_materials(session, owner.subject_id, {ep})
    session.commit()
    evidence = sources[0]['evidence'][0]
    root = f'/api/v1/workbench/subjects/{owner.subject_id}/narrative'
    body = dict(kind='story', title='一次讲述', text='本人留下的经历',
                evidence_ids=[evidence['evidence_id']], facets=['EXPERIENCE'],
                time_text='', place_text='', aliases=[], same_event=True, recipient_label='')
    return owner, reader, oh, rh, ep, cloud, root, body


def test_review_share_revoke_and_history(app, client, session):
    owner, reader, oh, rh, ep, cloud, root, body = prepare(app, client, session)
    assert client.post(root+'/records', headers=rh, json=body).status_code == 404
    r=client.post(root+'/records', headers=oh, json=body)
    assert r.status_code==201, r.text
    row=r.json(); assert row['status']=='pending'
    grant=client.post(root.removesuffix('/narrative')+'/grants',headers=oh,json={
        'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True}).json()
    assert client.get(root,headers=rh).json()['records']==[]
    confirmed=client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    assert confirmed.status_code==200, confirmed.text
    assert len(client.get(root,headers=rh).json()['records'])==1
    assert client.get(root+'/records/'+row['id']+'/history',headers=rh).status_code==404
    assert client.post(root+'/records/'+row['id']+'/reject',headers=rh,json={'revision':2}).status_code==404
    client.delete(root.removesuffix('/narrative')+'/grants/'+grant['grant_id'],headers=oh)
    assert client.get(root,headers=rh).status_code==404


def test_edit_requires_revision_and_review_and_undo_preserves_history(app,client,session):
    *_, oh, rh, ep, cloud, root, body = prepare(app,client,session)
    row=client.post(root+'/records',headers=oh,json=body).json();path=root+'/records/'+row['id']
    assert client.post(path+'/confirm',headers=oh,json={'revision':1}).status_code==200
    edited=client.put(path,headers=oh,json={**body,'title':'更正标题','revision':2})
    assert edited.status_code==200,edited.text
    assert edited.json()['status']=='pending'
    assert client.put(path,headers=oh,json={**body,'revision':2}).status_code==409
    undone=client.post(path+'/undo',headers=oh,json={'revision':3})
    assert undone.status_code==200,undone.text
    assert undone.json()['title']=='一次讲述' and undone.json()['status']=='pending'
    assert len(client.get(path+'/history',headers=oh).json()['items'])==4


def test_changed_deleted_or_foreign_evidence_never_revalidates(app,client,session):
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    assert client.post(root+'/records',headers=oh,json={**body,'evidence_ids':['foreign']}).status_code==422
    assert client.post(root+'/records',headers=oh,json={**body,'time_text':'2099年'}).status_code==422
    row=client.post(root+'/records',headers=oh,json=body).json()
    session.get(Episode,ep).transcript='完全改变的材料';session.commit()
    assert client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1}).status_code==409
    assert client.get(root,headers=oh).json()['records'][0]['status']=='stale'


def test_four_views_empty_facets_and_style_default(app,client,session):
    *_,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    response=client.get(root,headers=oh)
    assert response.status_code==200,response.text
    data=response.json()
    assert [v['title'] for v in data['views']]==['人生足迹','重要的人','在意与选择','声音与表达']
    assert len(data['facets'])==8
    assert data['style']['enabled'] is False
    assert data['next_question'] is None


def test_model_job_only_proposes_and_rejects_stale_publication(app,client,session):
    from app.profiles import run_profile_once
    from app.models import ProfileRefresh
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    class Provider:
        def propose_narrative(self,payload):
            return {'records':[body],'model_version':'test','prompt_version':'narrative-v1'}
    response=client.post(root+'/suggest',headers=oh,json={'cloud_consent_id':cloud,'episode_ids':[ep]})
    assert response.status_code==202,response.text
    run_profile_once(app.state.database,Provider())
    session.expire_all()
    assert session.get(ProfileRefresh,response.json()['job_id']).status=='complete'
    assert client.get(root,headers=oh).json()['records'][0]['status']=='pending'
    class Changing(Provider):
        def propose_narrative(self,payload):
            with app.state.database.session() as other:
                other.get(Episode,ep).transcript+='。新增内容';other.commit()
            return super().propose_narrative(payload)
    job=client.post(root+'/suggest',headers=oh,json={'cloud_consent_id':cloud}).json()['job_id']
    run_profile_once(app.state.database,Changing());session.expire_all()
    assert session.get(ProfileRefresh,job).status=='failed'
    assert len(client.get(root,headers=oh).json()['records'])==1


def test_partial_shared_story_derived_title_and_alias_never_leak(app,client,session):
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    secret=_record(client,app,owner.subject_id,owner.consent_id,oh)
    source=effective_materials(session,owner.subject_id,{secret})[0]['evidence'][0];session.commit()
    body.update(title='不能泄露的私密标题',evidence_ids=body['evidence_ids']+[source['evidence_id']])
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    client.post(root.removesuffix('/narrative')+'/grants',headers=oh,json={
        'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True})
    result=client.get(root,headers=rh)
    assert result.status_code==200 and '不能泄露' not in result.text and secret not in result.text


def test_same_event_repeated_tellings_count_once(app,client,session):
    from app.narrative import event_support,material_map
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    ep2=_record(client,app,owner.subject_id,owner.consent_id,oh)
    source=effective_materials(session,owner.subject_id,{ep2})[0]['evidence'][0];session.commit()
    body['evidence_ids'].append(source['evidence_id'])
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    sources=material_map(session,owner.subject_id,owner.actor_id)
    assert event_support(session,owner.subject_id,body['evidence_ids'],sources)==1


def test_style_requires_real_subject_quote_and_explicit_switch(app,client,session):
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    assert client.put(root+'/style',headers=oh,json={'enabled':True,'revision':0}).status_code==422
    body.update(kind='style',same_event=False,facets=['EXPRESSION'],text='编造的安慰话')
    assert client.post(root+'/records',headers=oh,json=body).status_code==422
    body['text']=effective_materials(session,owner.subject_id,{ep})[0]['evidence'][0]['excerpt'];session.commit()
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    assert client.put(root+'/style',headers=rh,json={'enabled':True,'revision':0}).status_code==404
    assert client.put(root+'/style',headers=oh,json={'enabled':True,'revision':0}).status_code==200
    assert client.put(root+'/style',headers=oh,json={'enabled':False,'revision':1}).status_code==200


def test_split_moves_sources_atomically_and_keeps_both_pending(app,client,session):
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    ep2=_record(client,app,owner.subject_id,owner.consent_id,oh)
    source=effective_materials(session,owner.subject_id,{ep2})[0]['evidence'][0];session.commit()
    first=body['evidence_ids'][0];body['evidence_ids'].append(source['evidence_id'])
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    split=client.post(root+'/records/'+row['id']+'/split',headers=oh,json={**body,'evidence_ids':[source['evidence_id']],'title':'拆出部分','revision':2})
    assert split.status_code==201,split.text
    records=client.get(root,headers=oh).json()['records']
    assert len(records)==2 and all(r['status']=='pending' for r in records)
    assert next(r for r in records if r['id']==row['id'])['evidence_ids']==[first]


def test_twin_receives_confirmed_context_but_never_pending(app,client,session):
    from test_twin_voice import QuoteTwin
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    body.update(kind='observation',same_event=False,text='这段经历的具体情境')
    record=client.post(root+'/records',headers=oh,json=body).json()
    class Inspect(QuoteTwin):
        traits=[]
        def answer(self,q,candidates):
            self.traits=[t for c in candidates for t in c['traits']]
            return super().answer(q,candidates)
    twin=Inspect();app.state.twin_client=twin
    query=lambda:client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,json={'question':'讲过什么？','cloud_consent_id':cloud})
    assert query().status_code==200 and not twin.traits
    client.post(root+'/records/'+record['id']+'/confirm',headers=oh,json={'revision':1})
    assert query().status_code==200
    assert any('这段经历的具体情境' in t for t in twin.traits)


def test_inflight_answer_cannot_survive_confirmed_story_change(app,client,session):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from fastapi.testclient import TestClient
    from test_twin_voice import QuoteTwin
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    started,release=Event(),Event()
    class Slow(QuoteTwin):
        def answer(self,*args):
            started.set();assert release.wait(15);return super().answer(*args)
    app.state.twin_client=Slow()
    def run():
        with TestClient(app) as other:
            return other.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,json={'question':'讲过什么？','cloud_consent_id':cloud})
    with ThreadPoolExecutor() as executor:
        pending=executor.submit(run);assert started.wait(15)
        try: assert client.post(root+'/records/'+row['id']+'/reject',headers=oh,json={'revision':2}).status_code==200
        finally: release.set()
        assert pending.result().status_code==409


def test_style_uses_only_confirmed_visible_examples_and_disable_invalidates(app,client,session):
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    excerpt=effective_materials(session,owner.subject_id,{ep})[0]['evidence'][0]['excerpt'];session.commit()
    body.update(kind='style',text=excerpt,facets=['EXPRESSION'],same_event=False)
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    client.put(root+'/style',headers=oh,json={'enabled':True,'revision':0})
    class StyleTwin:
        def answer(self,q,c):
            return dict(answer='他回忆了一段经历。',response_type='SIMULATION',evidence_ids=[c[0]['evidence'][0]['evidence_id']],confidence=.8,model_version='test')
        def express(self,answer,examples):
            assert examples==[{'id':row['id'],'text':excerpt}]
            return dict(status='available',text=answer,model_version='test',prompt_version='test')
    app.state.twin_client=StyleTwin()
    path=f'/api/v1/subjects/{owner.subject_id}/twin/answers'
    response=client.post(path,headers=oh,json={'question':'经历？','cloud_consent_id':cloud})
    assert response.status_code==200,response.text
    assert response.json()['expression']['status']=='available'
    client.put(root+'/style',headers=oh,json={'enabled':False,'revision':1})
    old=client.get(path+'/'+response.json()['answer_id'],headers=oh).json()
    assert old['stale'] and old['expression'] is None


def test_unassigned_evidence_is_not_proof_of_an_independent_event(app,client,session):
    from app.narrative import event_support,material_map
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    assert event_support(session,owner.subject_id,body['evidence_ids'],material_map(session,owner.subject_id,owner.actor_id))==0


def test_one_question_can_be_snoozed_and_reader_cannot_mutate(app,client,session):
    from app.models import QuestionRequest
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.add(QuestionRequest(request_id='qr_round2',subject_id=owner.subject_id,actor_id=reader.actor_id,text='那个水杯有什么故事？',status='pending'));session.commit()
    q=client.get(root,headers=oh).json()['next_question'];assert q['request_id']=='qr_round2'
    assert client.post(root+'/next-question',headers=rh,json={'id':q['id'],'action':'declined'}).status_code==404
    assert client.post(root+'/next-question',headers=oh,json={'id':q['id'],'action':'snoozed'}).status_code==200
    assert client.get(root,headers=oh).json()['next_question'] is None


def test_disabling_style_during_answer_prevents_a_new_expression_call(app,client,session):
    from app.models import NarrativePreference
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    excerpt=effective_materials(session,owner.subject_id,{ep})[0]['evidence'][0]['excerpt'];session.commit()
    row=client.post(root+'/records',headers=oh,json={**body,'kind':'style','text':excerpt,'same_event':False,'facets':['EXPRESSION']}).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    client.put(root+'/style',headers=oh,json={'enabled':True,'revision':0})
    class Changed:
        calls=0
        def answer(self,q,c):
            with app.state.database.session() as other:
                p=other.get(NarrativePreference,owner.subject_id);p.style_enabled=False;p.revision+=1;other.commit()
            return dict(answer='他留下了经历。',response_type='SIMULATION',evidence_ids=[c[0]['evidence'][0]['evidence_id']],confidence=.8,model_version='test')
        def express(self,*args):
            self.calls+=1;return {'status':'unavailable','text':''}
    model=Changed();app.state.twin_client=model
    response=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,json={'question':'往事？','cloud_consent_id':cloud})
    assert response.status_code==409
    assert model.calls==0


def test_temporal_change_invalidates_organized_current_interpretation(app,client,session):
    from sqlalchemy import select,delete
    from app.models import MemoryItem,MemoryRevision,PersonTrait,GraphFact
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    old.memory_type='PREFERENCE';old.item_metadata={'domain':'PREFERENCES'};session.commit()
    body.update(kind='observation',same_event=False,text='他喜欢散步。')
    record=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+record['id']+'/confirm',headers=oh,json={'revision':1})
    new_ep=_record(client,app,reader.subject_id,reader.consent_id,rh)
    session.get(Episode,new_ep).subject_id=owner.subject_id
    session.execute(delete(PersonTrait).where(PersonTrait.subject_id==reader.subject_id));session.execute(delete(GraphFact).where(GraphFact.subject_id==reader.subject_id))
    new=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==new_ep));new.memory_type='PREFERENCE';new.item_metadata={'domain':'PREFERENCES'};new.review_state='pending'
    session.add(MemoryRevision(revision_id='round2-change',subject_id=owner.subject_id,target_memory_id=old.memory_item_id,episode_id=new_ep,kind='change',time_text='最近'));session.commit()
    assert client.post(root.removesuffix('/narrative')+'/revisions/round2-change/confirm',headers=oh).status_code==200
    row=next(r for r in client.get(root,headers=oh).json()['records'] if r['id']==record['id'])
    assert row['status']=='stale' and not row['source_valid']


def test_browsing_is_not_blocked_by_the_model_context_limit(app,client,session):
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.get(Episode,ep).transcript += '这是一段比较长的有效讲述。'*2000;session.commit()
    assert client.get(root,headers=oh).status_code==200


def test_shared_draft_schema_matches_backend():
    import json
    from pathlib import Path
    from app.narrative import RecordInput
    path=Path(__file__).resolve().parents[3]/'packages/contracts/schemas/narrative-draft-v1.schema.json'
    assert json.loads(path.read_text(encoding='utf8'))==RecordInput.model_json_schema()


def test_mobile_response_follows_shared_contract(app,client,session):
    import json,jsonschema
    from pathlib import Path
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    row=client.post(root+'/records',headers=oh,json=body).json()
    client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1})
    client.post(root.removesuffix('/narrative')+'/grants',headers=oh,json={
        'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True})
    schema=json.loads((Path(__file__).resolve().parents[3]/'packages/contracts/schemas/narrative-overview-v1.schema.json').read_text(encoding='utf8'))
    jsonschema.validate(client.get(root,headers=oh).json(),schema)
    jsonschema.validate(client.get(root,headers=rh).json(),schema)


def test_optional_style_budget_never_blocks_fact_answer(app,client,session):
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    excerpt=effective_materials(session,owner.subject_id,{ep})[0]['evidence'][0]['excerpt'];session.commit()
    body.update(kind='style',text=excerpt,facets=['EXPRESSION'],same_event=False)
    for i in range(9):
        row=client.post(root+'/records',headers=oh,json={**body,'title':f'范例{i}'}).json()
        assert client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':1}).status_code==200
    client.put(root+'/style',headers=oh,json={'enabled':True,'revision':0})
    class Twin:
        def answer(self,q,c):
            return dict(answer='他回忆了一段经历。',response_type='SIMULATION',evidence_ids=[c[0]['evidence'][0]['evidence_id']],confidence=.8,model_version='test')
        def express(self,*args): raise AssertionError('Over-budget optional generation must not run')
    app.state.twin_client=Twin()
    response=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,json={'question':'经历？','cloud_consent_id':cloud})
    assert response.status_code==200,response.text
    assert response.json()['answer']=='他回忆了一段经历。'
    assert response.json()['expression']['status']=='unavailable'


def test_selected_cloud_batch_does_not_send_unselected_long_story(app,client,session):
    from app.profiles import run_profile_once
    from app.models import ProfileRefresh,MemoryRevision,MemoryItem
    from sqlalchemy import select
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    unselected=_record(client,app,owner.subject_id,owner.consent_id,oh)
    session.get(Episode,unselected).transcript += '不可发送的另一段长记录。'*2500
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.add(MemoryRevision(revision_id='unselected-time-context',subject_id=owner.subject_id,target_memory_id=old.memory_item_id,
        episode_id=unselected,kind='change',status='confirmed',time_text='未选日期2039'))
    session.commit()
    class Provider:
        called=False
        def propose_narrative(self,payload):
            self.called=True
            assert {m['episode_id'] for m in payload['materials']}=={ep}
            assert not any('不可发送' in m['excerpt'] for m in payload['materials'])
            assert '2039' not in str(payload)
            return {'records':[body],'model_version':'test','prompt_version':'test'}
    provider=Provider()
    job=client.post(root+'/suggest',headers=oh,json={'cloud_consent_id':cloud,'episode_ids':[ep]}).json()
    run_profile_once(app.state.database,provider);session.expire_all()
    assert provider.called and session.get(ProfileRefresh,job['job_id']).status=='complete'
    row=client.get(root,headers=oh).json()['records'][0]
    assert row['source_valid'] and row['status']=='pending'
    assert client.post(root+'/records/'+row['id']+'/confirm',headers=oh,json={'revision':row['revision']}).status_code==200


def test_private_change_time_does_not_leak_through_public_source_context(app,client,session):
    from sqlalchemy import select
    from app.models import MemoryItem,MemoryRevision
    from test_twin_voice import _record
    owner,reader,oh,rh,ep,cloud,root,body=prepare(app,client,session)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    private=_record(client,app,owner.subject_id,owner.consent_id,oh)
    session.add(MemoryRevision(revision_id='private-change-time',subject_id=owner.subject_id,target_memory_id=old.memory_item_id,
        episode_id=private,kind='change',status='confirmed',time_text='私人日期2039年3月2日'));session.commit()
    assert client.post(root.removesuffix('/narrative')+'/grants',headers=oh,json={
        'episode_id':ep,'reader_actor_id':reader.actor_id,'include_audio_confirmed':True}).status_code==201
    response=client.get(root,headers=rh)
    assert response.status_code==200
    assert '2039' not in response.text and '私人日期' not in response.text and private not in response.text
