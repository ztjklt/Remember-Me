from datetime import timedelta
import pytest
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


def noisy_history_with_latest_tail(session,prototype,*,latest_count=8,tail_answer=None):
    """Older greeting matches outrank an unrelated latest conversation."""
    base=utcnow();prototype.created_at=base-timedelta(minutes=5)
    values={c.name:getattr(prototype,c.name) for c in TwinAnswer.__table__.columns}
    for n in range(24):
        session.add(TwinAnswer(**dict(values,answer_id=f'greeting_noise_{n}',conversation_id='tc_greeting_noise',
            question=f'你好，这是以前的普通寒暄{n}',request_id=None,parent_answer_id=None,
            created_at=base-timedelta(minutes=3)+timedelta(microseconds=n))))
    latest=[]
    for n in range(latest_count):
        identifier=f'latest_tail_{n}';latest.append(identifier)
        session.add(TwinAnswer(**dict(values,answer_id=identifier,question=f'书签的新安排第{n}项',
            answer=tail_answer if tail_answer is not None else '这是当前对话的回应。',
            request_id=None,parent_answer_id=None,created_at=base-timedelta(minutes=1)+timedelta(microseconds=n))))
    session.commit();return latest


def test_optional_latest_tail_reservation_beats_low_relevance_and_keeps_shared_budget(app,client,session):
    from app import chat_memory
    from app.twin_basis import current
    owner,_,oh,_,cloud,_=setup(app,client,session)
    original=send(client,owner,oh,cloud,'书签的计划。').json()
    tail=noisy_history_with_latest_tail(session,session.get(TwinAnswer,original['answer_id']))
    args=(session,owner.subject_id,owner.actor_id,current(session,owner.subject_id),'你好',[],app.state.embedding_encoder)
    ordinary,_,_=chat_memory.prepare(*args)
    assert not set(tail).intersection(t['answer_id'] for t in ordinary)
    carried,_,_=chat_memory.prepare(*args,carry_latest_conversation=True)
    ids={t['answer_id'] for t in carried}
    assert set(tail[-6:])<=ids
    assert not set(tail[:-6]).intersection(ids)
    assert any(t['answer_id'].startswith('greeting_noise_') for t in carried)
    assert len(carried)<=12 and sum(len(t['question'])+len(t['answer'] or '') for t in carried)<=10000
    assert carried==sorted(carried,key=lambda t:(t['created_at'],t['answer_id']))


def test_latest_tail_reservation_cannot_exceed_character_budget_or_reuse_stale_assistant(app,client,session):
    from app import chat_memory
    from app.twin_basis import current
    owner,_,oh,_,cloud,_=setup(app,client,session)
    original=send(client,owner,oh,cloud,'书签的计划。').json()
    tail=noisy_history_with_latest_tail(session,session.get(TwinAnswer,original['answer_id']),tail_answer='长'*2200)
    row=session.get(TwinAnswer,tail[-1]);row.answer='失效回复中的秘密';row.invalidated_at=utcnow();session.commit()
    recalled,_,_=chat_memory.prepare(session,owner.subject_id,owner.actor_id,current(session,owner.subject_id),
        '你好',[],app.state.embedding_encoder,carry_latest_conversation=True)
    assert tail[-1] in {t['answer_id'] for t in recalled}
    assert sum(len(t['question'])+len(t['answer'] or '') for t in recalled)<=10000
    assert '失效回复中的秘密' not in str(recalled)
    assert len(set(tail[-6:]).intersection(t['answer_id'] for t in recalled))<6


def test_unsaved_prediction_cannot_enable_latest_conversation_carry_even_if_internal_flag_is_set(app,client,session,monkeypatch):
    from starlette.requests import Request
    from app import chat_memory
    from app.models import Actor
    from app.api.twin import answer_question,TwinQuestion
    owner,_,oh,_,cloud,twin=setup(app,client,session)
    first=send(client,owner,oh,cloud,'书签的计划。').json()
    tail=noisy_history_with_latest_tail(session,session.get(TwinAnswer,first['answer_id']))
    flags=[];original=chat_memory.prepare
    def inspect(*args,**kwargs):
        flags.append(kwargs.get('carry_latest_conversation'));return original(*args,**kwargs)
    monkeypatch.setattr(chat_memory,'prepare',inspect)
    result=answer_question(owner.subject_id,TwinQuestion(question='你好',cloud_consent_id=cloud,conversation_mode=True),
        Request({'type':'http','app':app}),session.get(Actor,owner.actor_id),session,
        chat_history_scope='actor',persist_answer=False,carry_latest_conversation=True)
    assert flags==[False]
    assert not set(tail).intersection(t['answer_id'] for t in twin.options[-1]['conversation_recall'])
    assert session.get(TwinAnswer,result['answer_id']) is None


@pytest.mark.parametrize('question',[
    '总结以前聊过的内容','回顾一下我们以前的聊天。','概括我们之前聊了什么？',
    '我以前聊过什么？','以前我们聊过哪些内容？','请简单总结所有聊天记录。',
    '我们以前都聊过什么？','总结以前聊过的内容\n前文提问主题（不是本人事实）：\n橙色书签',
])
def test_only_generic_chat_recaps_use_chronological_coverage(question):
    from app.chat_memory import is_general_overview
    assert is_general_overview(question) is True


@pytest.mark.parametrize('question',[
    '我以前聊过什么颜色的书签？','总结以前聊过的王明。','回顾2026-10-14的聊天。',
    '我之前聊过哪些关于王明的内容？','概括以前聊过的probe_topic_837内容。',
    '总结昨天聊过的内容。','总结最近聊过的内容。','回顾一下今年关于旅行的聊天。',
    '我以前聊过什么颜色的书签？\n前文提问主题（不是本人事实）：\n总结所有聊天',
])
def test_named_topic_person_date_or_tag_does_not_trigger_whole_history_sampling(question):
    from app.chat_memory import is_general_overview
    assert is_general_overview(question) is False


@pytest.mark.parametrize('keyword,question',[
    ('书签','我以前聊过什么颜色的书签？'),
    ('2026-10-14','回顾2026-10-14的聊天内容。'),
    ('王明','总结以前聊过的王明。'),
    ('probe_topic_837','概括以前聊过的probe_topic_837内容。'),
])
def test_targeted_recap_keeps_topic_source_that_uniform_sampling_would_skip(app,client,session,keyword,question):
    owner,_,oh,_,cloud,twin=setup(app,client,session)
    first,_=old_chain(client,session,owner,oh,cloud,60)
    session.get(TwinAnswer,first['answer_id']).question='一段普通寒暄。'
    source=session.get(TwinAnswer,'old_13');source.question=f'本人提到{keyword}，这段原消息应被相关性检索选中。'
    session.commit()
    class KeywordEncoder:
        version='overview-targeted-test'
        def encode(self,texts):return [[8.*float(keyword in text),1.] for text in texts]
    app.state.embedding_encoder=KeywordEncoder()
    result=send(client,owner,oh,cloud,question)
    assert result.status_code==200,result.text
    assert 'old_13' in result.json()['recalled_answer_ids']
    recalled=twin.options[-1]['conversation_recall']
    assert any(t['answer_id']=='old_13' and keyword in t['question'] for t in recalled)
