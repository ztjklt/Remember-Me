from datetime import timedelta
from sqlalchemy import select, func
from app.models import TwinAnswer, ChatTurnEmbedding, ChatDigest, utcnow
from test_agent_workbench import setup_pair
from test_twin_conversation import send, Dialogue


class RecallTwin(Dialogue):
    def __init__(self): super().__init__(); self.options=[]; self.summaries=0
    def answer(self, question, candidates, **kwargs):
        self.options.append(kwargs)
        return super().answer(question,candidates,**kwargs)
    def summarize_chat(self, turns):
        self.summaries+=1
        return {'summary':'旧聊天中本人提及：'+turns[0]['question'],'model_version':'fake-summary'}


class TopicEncoder:
    version='chat-topic-test'
    def encode(self, texts):
        return [[float('书签' in t)*8,float('散步' in t)*8,1.] for t in texts]


def setup(app,client,session):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    twin=RecallTwin();app.state.twin_client=twin;app.state.embedding_encoder=TopicEncoder()
    return owner,reader,oh,rh,cloud,twin


def old_chain(client,session,owner,oh,cloud,count=25):
    first=send(client,owner,oh,cloud,'我喜欢橙色书签，但不喜欢紫色。').json()
    prototype=session.get(TwinAnswer,first['answer_id']);parent=first['answer_id']
    for n in range(count):
        values={c.name:getattr(prototype,c.name) for c in TwinAnswer.__table__.columns}
        values.update(answer_id=f'old_{n}',question=f'讨论散步路线{n}',parent_answer_id=parent,
            request_id=None,created_at=utcnow()+timedelta(microseconds=n))
        session.add(TwinAnswer(**values));parent=f'old_{n}'
    session.commit()
    return first,parent


def test_recalls_message_older_than_twenty_and_across_new_chats(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    first,parent=old_chain(client,session,owner,oh,cloud)
    result=send(client,owner,oh,cloud,'我以前说过喜欢什么颜色的书签？',parent)
    assert result.status_code==200,result.text
    recalled=twin.options[-1]['conversation_recall']
    assert first['answer_id'] in {t['answer_id'] for t in recalled}
    assert first['answer_id'] not in {t['answer_id'] for t in twin.options[-1]['conversation_turns']}
    assert result.json()['recalled_turn_count']>0 and result.json()['history_summary_status']=='ready'
    assert twin.summaries==1 and session.scalar(select(func.count()).select_from(ChatDigest))==1
    assert twin.options[-1]['conversation_summary']
    fresh=send(client,owner,oh,cloud,'橙色书签是以前哪次聊的？')
    assert fresh.status_code==200,fresh.text
    assert twin.options[-1]['conversation_turns']==[]
    assert any(t['answer_id']==first['answer_id'] for t in twin.options[-1]['conversation_recall'])


def test_history_inspection_search_switch_and_clear_prevent_reindex(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    first=send(client,owner,oh,cloud,'我喜欢橙色书签。').json()
    send(client,owner,oh,cloud,'以前的书签偏好是什么？')
    path=f'/api/v1/subjects/{owner.subject_id}/twin/chat-memory'
    view=client.get(path,headers=oh,params={'cloud_consent_id':cloud,'q':'书签'})
    assert view.status_code==200 and view.json()['items'] and view.json()['summaries']
    assert client.get(path,headers=rh,params={'cloud_consent_id':cloud}).status_code==404
    assert client.put(path,headers=rh,json={'enabled':False}).status_code==404
    assert client.put(path,headers=oh,json={'enabled':False}).status_code==200
    send(client,owner,oh,cloud,'书签之前聊过吗？')
    assert not twin.options[-1].get('conversation_recall')
    assert client.put(path,headers=oh,json={'enabled':True}).status_code==200
    assert client.delete(path,headers=oh).status_code==200
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(ChatTurnEmbedding))==0
    assert session.scalar(select(func.count()).select_from(ChatDigest))==0
    # Even a parent pointing to a cleared original cannot reintroduce its text.
    response=send(client,owner,oh,cloud,'继续聊',first['answer_id'])
    assert response.status_code==200,response.text
    assert not twin.options[-1].get('conversation_recall') and twin.options[-1]['conversation_turns']==[]
    assert '橙色' not in str(twin.options[-1])
    view=client.get(path,headers=oh,params={'cloud_consent_id':cloud}).json()
    assert all('橙色' not in t['question'] for t in view['items'])


def test_summary_failure_still_uses_exact_messages(app,client,session):
    from app.twin_client import TwinUnavailable
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    def fail(turns):raise TwinUnavailable('unavailable')
    twin.summarize_chat=fail
    send(client,owner,oh,cloud,'我喜欢橙色书签。')
    result=send(client,owner,oh,cloud,'书签是什么颜色？')
    assert result.status_code==200,result.text
    assert result.json()['history_summary_status']=='unavailable'
    assert twin.options[-1]['conversation_recall'] and not twin.options[-1].get('conversation_summary')


def test_expired_assistant_not_indexed_or_summarized_and_revoke_blocks_access(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    first=send(client,owner,oh,cloud,'我喜欢橙色书签。').json()
    row=session.get(TwinAnswer,first['answer_id']);row.answer='不可重用的秘密';row.invalidated_at=utcnow();session.commit()
    result=send(client,owner,oh,cloud,'以前的书签偏好？')
    assert result.status_code==200,result.text
    assert '不可重用' not in str(twin.options[-1])
    recalled=next(t for t in twin.options[-1]['conversation_recall'] if t['answer_id']==first['answer_id'])
    assert recalled['answer'] is None and recalled['assistant_stale']
    client.post('/api/v1/consents/'+cloud+'/revoke',headers=oh)
    assert client.get(f'/api/v1/subjects/{owner.subject_id}/twin/chat-memory',headers=oh,params={'cloud_consent_id':cloud}).status_code in {403,404}
    assert send(client,owner,oh,cloud,'书签').status_code in {403,404}


def test_clear_during_summary_cannot_publish_or_save_digest(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    send(client,owner,oh,cloud,'我喜欢橙色书签。')
    def clear(turns):
        result=client.delete(f'/api/v1/subjects/{owner.subject_id}/twin/chat-memory',headers=oh)
        assert result.status_code==200
        return {'summary':'橙色书签','model_version':'fake-summary'}
    twin.summarize_chat=clear
    result=send(client,owner,oh,cloud,'我之前的书签偏好？')
    assert result.status_code==409,result.text
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(ChatDigest))==0


def test_other_actor_history_never_enters_owner_recall(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    other=client.post('/api/v1/consents',headers=rh,json={'subject_id':reader.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    foreign=send(client,reader,rh,other,'我秘密喜欢橙色书签。').json()
    result=send(client,owner,oh,cloud,'书签')
    assert result.status_code==200,result.text
    assert not twin.options[-1].get('conversation_recall')
    assert foreign['answer_id'] not in result.json()['recalled_answer_ids']


def test_changed_source_purges_derived_chat_caches_without_erasing_user_messages(app,client,session):
    from app.retrieval import invalidate_answers
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    first=send(client,owner,oh,cloud,'我喜欢橙色书签。').json()
    send(client,owner,oh,cloud,'书签是什么颜色？')
    assert session.scalar(select(func.count()).select_from(ChatDigest))>0
    invalidate_answers(session,app.state.object_store,owner.subject_id);session.commit()
    assert session.scalar(select(func.count()).select_from(ChatDigest))==0
    assert session.scalar(select(func.count()).select_from(ChatTurnEmbedding))==0
    assert session.get(TwinAnswer,first['answer_id']).question=='我喜欢橙色书签。'


def test_general_history_summary_retrieves_topics_from_across_time(app,client,session):
    owner,reader,oh,rh,cloud,twin=setup(app,client,session)
    first,parent=old_chain(client,session,owner,oh,cloud,60)
    result=send(client,owner,oh,cloud,'总结以前聊过的内容')
    assert result.status_code==200,result.text
    recalled=twin.options[-1]['conversation_recall']
    assert first['answer_id'] in {t['answer_id'] for t in recalled}
    assert 'old_59' in {t['answer_id'] for t in recalled} and len(recalled)<=12
