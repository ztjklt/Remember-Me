from types import SimpleNamespace
from sqlalchemy import select
from app.models import Evidence
from test_companion import prepare, post


def setup(app, client, session):
    owner, reader, other, oh, rh, xh, ep, root = prepare(app, client, session)
    letter = post(client, root+'/letters', oh, dict(idempotency_key='recall',
        recipient_actor_id=reader.actor_id, title='灯一直亮着', text='只留给你的缘由。'), 201)
    letter = post(client, root+'/letters/'+letter['id']+'/publish', oh, dict(revision=1, confirmed=True))
    eid = session.scalar(select(Evidence.evidence_id).where(Evidence.episode_id == ep))
    return owner, reader, other, oh, rh, xh, root, letter, eid


def test_opt_in_requires_owner_and_current_published_letter(app, client, session):
    o,r,x,oh,rh,xh,root,l,e = setup(app,client,session)
    path=root+'/letters/'+l['id']+'/recall'
    body=dict(revision=l['revision'], evidence_ids=[e])
    assert client.put(path,headers=rh,json=body).status_code==404
    assert client.put(path,headers=oh,json={**body,'evidence_ids':['foreign']}).status_code==404
    assert client.put(path,headers=oh,json={**body,'revision':1}).status_code==409
    assert client.put(path,headers=oh,json=body).status_code==200


def test_recall_is_scoped_to_answer_sources_actor_and_live_letter(app, client, session):
    from app.entrusted_recall import recall_actions
    o,r,x,oh,rh,xh,root,l,e = setup(app,client,session)
    row=SimpleNamespace(subject_id=o.subject_id,actor_id=r.actor_id,evidence_ids=[e],invalidated_at=None,response_type='FACT')
    assert recall_actions(session,row)==[]
    assert client.put(root+'/letters/'+l['id']+'/recall',headers=oh,json=dict(revision=l['revision'],evidence_ids=[e])).status_code==200
    session.expire_all()
    actions=recall_actions(session,row)
    assert len(actions)==1 and actions[0]['letter_id']==l['id']
    assert '只留给你的缘由' not in str(actions)
    row.actor_id=x.actor_id
    assert recall_actions(session,row)==[]
    row.actor_id=r.actor_id;row.evidence_ids=[]
    assert recall_actions(session,row)==[]
    row.evidence_ids=[e];row.response_type='UNKNOWN'
    assert recall_actions(session,row)==[]
    row.response_type='FACT';row.invalidated_at=True
    assert recall_actions(session,row)==[]
    row.invalidated_at=None
    post(client,root+'/letters/'+l['id']+'/revoke',oh,dict(revision=l['revision']))
    session.expire_all()
    assert recall_actions(session,row)==[]


def test_material_change_disables_prior_owner_association(app, client, session):
    from app.entrusted_recall import recall_actions
    o,r,x,oh,rh,xh,root,l,e = setup(app,client,session)
    assert client.put(root+'/letters/'+l['id']+'/recall',headers=oh,json=dict(revision=l['revision'],evidence_ids=[e])).status_code==200
    session.expire_all()
    source=session.get(Evidence,e);source.excerpt+='后来已更正';session.commit()
    row=SimpleNamespace(subject_id=o.subject_id,actor_id=r.actor_id,evidence_ids=[e],invalidated_at=None,response_type='FACT')
    assert recall_actions(session,row)==[]
