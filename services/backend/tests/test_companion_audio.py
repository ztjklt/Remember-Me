from sqlalchemy import select
from test_companion import prepare, permission, post
from app.models import Episode, MemoryItem


def upload(client,root,h,purpose='contribution',key='audio-1'):
    r=client.post(root+'/audio',headers=h,data={'purpose':purpose,'idempotency_key':key},
        files={'file':('sample.wav',b'OWN-TEST-AUDIO','audio/wav')})
    assert r.status_code==201,r.text
    return r.json()


def test_signed_audio_saved_before_asr_private_and_immutable_after_attachment(app,client,session):
    o,c,r,oh,ch,rh,ep,root=prepare(app,client,session);permission(client,root,oh,c)
    before=session.query(Episode).count();memories=session.query(MemoryItem).count()
    a=upload(client,root,ch);path=root+'/audio/'+a['audio_id']
    assert a['status']=='saved' and a['transcript_text']==''
    assert client.get(path+'/content',headers=rh).status_code==404
    assert upload(client,root,ch)['audio_id']==a['audio_id']
    app.state.settings.stt_backend='http'
    trans=post(client,path+'/transcribe',ch,{'cloud_asr_policy':'test'})
    assert trans['transcript_text'] and trans['status']=='reviewing'
    reviewed=client.put(path+'/review',headers=ch,json={'revision':trans['revision'],'text':'父亲总先检查原因，这是我的回忆。'})
    assert reviewed.status_code==200,reviewed.text
    n=post(client,root+'/contributions',ch,{'idempotency_key':'from-audio','classification':'firsthand',
        'text':reviewed.json()['reviewed_text'],'audio_id':a['audio_id']},201)
    assert n['audio_id']==a['audio_id']
    assert client.put(path+'/review',headers=ch,json={'revision':reviewed.json()['revision'],'text':'换个说法'}).status_code==409
    accepted=post(client,root+'/contributions/'+n['id']+'/review',oh,{'revision':n['revision'],'decision':'accepted'})
    response=client.put(root+'/contributions/'+n['id']+'/recipients',headers=oh,
        json={'revision':accepted['revision'],'recipient_actor_ids':[r.actor_id]})
    assert response.status_code==200,response.text
    assert client.get(path+'/content',headers=rh).content==b'OWN-TEST-AUDIO'
    post(client,root+'/contributions/'+n['id']+'/withdraw',ch,{'revision':response.json()['revision']})
    assert client.get(path+'/content',headers=rh).status_code==404
    assert session.query(Episode).count()==before and session.query(MemoryItem).count()==memories


def test_note_model_permission_is_explicit_from_both_owner_and_author(app,client,session):
    o,c,r,oh,ch,rh,ep,root=prepare(app,client,session);permission(client,root,oh,c)
    n=post(client,root+'/contributions',ch,{'idempotency_key':'n','classification':'opinion','text':'我觉得他喜欢热闹。'},201)
    path=root+'/contributions/'+n['id']
    n=post(client,path+'/review',oh,{'revision':n['revision'],'decision':'accepted'})
    from app.persona_context import visible_contributions
    assert visible_contributions(session,o.subject_id,o.actor_id)==[];session.commit()
    n=client.put(path+'/model-use',headers=oh,json={'revision':n['revision'],'allowed':True}).json()
    assert n['model_use_owner_allowed'] and not n['model_use_author_allowed']
    assert visible_contributions(session,o.subject_id,o.actor_id)==[];session.commit()
    n=client.put(path+'/model-use',headers=ch,json={'revision':n['revision'],'allowed':True}).json()
    assert n['model_use_author_allowed']
    selected=visible_contributions(session,o.subject_id,o.actor_id);session.commit()
    assert selected[0]['author_name']=='读者' and selected[0]['classification']=='opinion'
    assert visible_contributions(session,o.subject_id,r.actor_id)==[];session.commit()
    n=client.put(path+'/model-use',headers=ch,json={'revision':n['revision'],'allowed':False}).json()
    assert visible_contributions(session,o.subject_id,o.actor_id)==[]


def test_letter_audio_cannot_attach_foreign_or_unreviewed_recording(app,client,session):
    o,c,r,oh,ch,rh,ep,root=prepare(app,client,session);permission(client,root,oh,c)
    a=upload(client,root,ch)
    body={'idempotency_key':'letter','recipient_actor_id':r.actor_id,'title':'给你','text':'你好','audio_id':a['audio_id']}
    assert client.post(root+'/letters',headers=oh,json=body).status_code==404
    own=upload(client,root,oh,purpose='letter',key='own')
    assert client.post(root+'/letters',headers=oh,json=body|{'audio_id':own['audio_id']}).status_code==409
