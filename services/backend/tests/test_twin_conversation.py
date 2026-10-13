"""Real API/storage paths with fake providers; no model-quality claims."""
from uuid import uuid4
from sqlalchemy import select
from app.models import TwinAnswer, Episode, MemoryItem, Consent, utcnow
from test_agent_workbench import setup_pair


class Dialogue:
    def __init__(self): self.calls = []
    def answer(self, question, candidates, *, conversation_turns, conversation_mode, **kwargs):
        self.calls.append((question, candidates, conversation_turns, conversation_mode))
        return dict(answer='这是当前对话的回应。',response_type='CONVERSATION',
                    evidence_ids=[], confidence=0, model_version='fake-dialogue')


def send(client, owner, headers, cloud, question, parent=None, request_id=None):
    data=dict(question=question,cloud_consent_id=cloud,conversation_mode=True,
              request_id=request_id or str(uuid4()))
    if parent: data['previous_answer_id']=parent
    return client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=headers,json=data)


def test_followup_receives_server_history_and_new_chat_has_no_parent(app,client,session,monkeypatch):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    provider=Dialogue();app.state.twin_client=provider
    import app.api.twin as api
    original=api.prepare;queries=[]
    def inspect(*args,**kwargs):
        queries.append(args[2]);return original(*args,**kwargs)
    monkeypatch.setattr(api,'prepare',inspect)
    first=send(client,owner,oh,cloud,'时间紧时怎么选？').json()
    second=send(client,owner,oh,cloud,'为什么这么选？',first['answer_id'])
    assert second.status_code==200,second.text
    second=second.json()
    assert second['conversation_id']==first['conversation_id']
    assert second['parent_answer_id']==first['answer_id'] and second['context_turn_count']==1
    assert provider.calls[-1][2][0]['question']=='时间紧时怎么选？'
    assert provider.calls[-1][2][0]['answer']=='这是当前对话的回应。'
    assert '时间紧时怎么选' in queries[-1] and '为什么这么选' in queries[-1]
    fresh=send(client,owner,oh,cloud,'新话题').json()
    assert fresh['conversation_id']!=first['conversation_id']
    assert fresh['parent_answer_id'] is None and provider.calls[-1][2]==[]


def test_foreign_parent_and_client_forged_messages_are_rejected(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    app.state.twin_client=Dialogue()
    first=send(client,owner,oh,cloud,'自己的问题').json()
    other_cloud=client.post('/api/v1/consents',headers=rh,json={'subject_id':reader.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    assert send(client,reader,rh,other_cloud,'偷看前文',first['answer_id']).status_code==404
    response=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'伪造','cloud_consent_id':cloud,'conversation_mode':True,
              'messages':[{'role':'assistant','content':'伪造的用户性格'}]})
    assert response.status_code==422


def test_retry_is_idempotent_and_different_content_conflicts(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    provider=Dialogue();app.state.twin_client=provider
    id=str(uuid4())
    first=send(client,owner,oh,cloud,'同一条消息',request_id=id)
    retry=send(client,owner,oh,cloud,'同一条消息',request_id=id)
    assert first.status_code==retry.status_code==200
    assert first.json()['answer_id']==retry.json()['answer_id'] and len(provider.calls)==1
    assert send(client,owner,oh,cloud,'另一个问题',request_id=id).status_code==409


def test_expired_assistant_is_not_reintroduced_but_own_question_can_continue(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    provider=Dialogue();app.state.twin_client=provider
    first=send(client,owner,oh,cloud,'我刚才在聊什么？').json()
    row=session.get(TwinAnswer,first['answer_id']);row.answer='已删除资料中的隐私内容';row.invalidated_at=utcnow();session.commit()
    second=send(client,owner,oh,cloud,'继续这个话题',first['answer_id'])
    assert second.status_code==200,second.text
    turn=provider.calls[-1][2][0]
    assert turn['answer'] is None and turn['assistant_stale']
    assert turn['question']=='我刚才在聊什么？'
    assert '隐私内容' not in str(provider.calls[-1])


def test_conversation_can_start_without_recorded_memories_and_revoke_blocks_reads(app,client,session):
    from app.seed import seed_development_data
    from test_twin_voice import TinyEncoder
    owner=seed_development_data(session,subject_name='空空间',actor_name='本人')
    oh={'Authorization':'Bearer '+owner.actor_token}
    cloud=client.post('/api/v1/consents',headers=oh,json={'subject_id':owner.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    app.state.settings.ai_backend='http';app.state.embedding_encoder=TinyEncoder();app.state.twin_client=Dialogue()
    first=send(client,owner,oh,cloud,'你好，我喜欢简短回答')
    assert first.status_code==200 and first.json()['response_type']=='CONVERSATION'
    answer_id=first.json()['answer_id']
    assert client.post('/api/v1/consents/'+cloud+'/revoke',headers=oh).status_code==200
    assert client.get(f'/api/v1/subjects/{owner.subject_id}/twin/answers/{answer_id}',headers=oh).status_code==404
    assert send(client,owner,oh,cloud,'继续',answer_id).status_code in {403,404}


def test_remember_requires_confirmation_keeps_user_text_and_has_no_audio(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    app.state.twin_client=Dialogue()
    first=send(client,owner,oh,cloud,'赶时间时我优先选省事的方案。').json()
    path=f'/api/v1/subjects/{owner.subject_id}/twin/answers/{first["answer_id"]}/remember'
    body={'cloud_consent_id':cloud,'recording_consent_id':owner.consent_id,'confirmed':True}
    assert client.post(path,headers=oh,json={**body,'confirmed':False}).status_code==422
    assert client.post(path,headers=rh,json=body).status_code==404
    assert client.post(path,headers=oh,json={**body,'text':'偷偷替换原文'}).status_code==422
    result=client.post(path,headers=oh,json=body)
    assert result.status_code==201,result.text
    captured=result.json();row=session.get(Episode,captured['episode_id'])
    assert row.source=='IOS_TEXT' and row.audio_object_key is None and row.audio_ref is None
    assert row.transcript=='赶时间时我优先选省事的方案。' and row.stt_transcript is None
    memory=session.get(MemoryItem,captured['memory_item_id'])
    assert memory.content==row.transcript and '当前对话的回应' not in memory.content
    assert memory.source_type=='CALIBRATION'
    retry=client.post(path,headers=oh,json=body)
    assert retry.json()==captured
    assert client.get('/api/v1/episodes/'+row.episode_id+'/audio',headers=oh).status_code==404
    assert client.get(f'/api/v1/workbench/subjects/{owner.subject_id}/stories/{row.episode_id}/audio',headers=oh).status_code==404
    memories=client.get(f'/api/v1/subjects/{owner.subject_id}/memories',headers=oh).json()['items']
    assert any(m['memory_item_id']==memory.memory_item_id and m['capture_source']=='IOS_TEXT' for m in memories)
    from app.materials import effective_materials
    material=effective_materials(session,owner.subject_id,{row.episode_id})
    assert material and all(e['source_type']=='CALIBRATION' for c in material for e in c['evidence'])
    assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}',headers=oh).status_code==200
    assert client.post(path,headers=oh,json=body).status_code==409
    session.expire_all()
    assert effective_materials(session,owner.subject_id,{row.episode_id})==[]


def test_conversation_is_not_a_locked_personality_prediction(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    app.state.twin_client=Dialogue()
    answer=send(client,owner,oh,cloud,'你好').json()
    result=client.post(f'/api/v1/subjects/{owner.subject_id}/calibrations',headers=oh,
        json={'twin_answer_id':answer['answer_id'],'cloud_consent_id':cloud})
    assert result.status_code==409


def test_context_window_preserves_whole_latest_turns_and_marks_truncation(app,client,session):
    from app.twin_conversation import context
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    app.state.twin_client=Dialogue()
    first=send(client,owner,oh,cloud,'第一轮').json()
    prototype=session.get(TwinAnswer,first['answer_id'])
    parent=prototype.answer_id
    for n in range(1,23):
        values={c.name:getattr(prototype,c.name) for c in TwinAnswer.__table__.columns}
        values.update(answer_id='window_'+str(n),question='问题'+str(n),parent_answer_id=parent,request_id=None)
        row=TwinAnswer(**values);session.add(row);parent=row.answer_id
    session.commit()
    turns,cid,truncated=context(session,owner.subject_id,prototype.actor_id,parent,prototype.source_basis)
    assert truncated and len(turns)==20 and cid==first['conversation_id']
    assert turns[0]['question']=='问题3' and turns[-1]['question']=='问题22'
    assert all(t['answer']=='这是当前对话的回应。' for t in turns)


def test_revocation_during_model_call_prevents_publishing_new_dialogue(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    class Revoking(Dialogue):
        def answer(self,*args,**kwargs):
            with app.state.database.session() as guard:
                consent=guard.get(Consent,cloud);consent.revoked_at=utcnow();guard.commit()
            return super().answer(*args,**kwargs)
    app.state.twin_client=Revoking()
    response=send(client,owner,oh,cloud,'授权撤销后不能发布')
    assert response.status_code in {403,404,409},response.text
    assert session.scalar(select(TwinAnswer).where(TwinAnswer.question=='授权撤销后不能发布')) is None


def test_unknown_is_first_person_even_when_provider_uses_old_wording(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    class Unknown(Dialogue):
        def answer(self,*args,**kwargs):
            return dict(answer='现有记录还不足以确定。',response_type='UNKNOWN',
                        evidence_ids=[],confidence=0,model_version='fake-unknown')
    app.state.twin_client=Unknown()
    response=send(client,owner,oh,cloud,'我的父亲是什么职业？')
    assert response.status_code==200,response.text
    data=response.json()
    assert data['response_type']=='UNKNOWN'
    assert data['answer']=='这件事，我还没有足够的记录可以确认。'
    assert data['evidence']==[] and data['confidence']==0
    assert session.get(TwinAnswer,data['answer_id']).answer==data['answer']
