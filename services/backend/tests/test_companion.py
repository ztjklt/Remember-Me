"""Deterministic consent/attribution tests; fixtures are not live model evidence."""
import importlib.util
import pytest
from sqlalchemy import select
from app.models import MemoryItem, Episode, ProfileCandidate, NarrativeRecord, utcnow
from app.seed import seed_development_data
from app.access import profile_source_basis
from app.narrative import material_map, fingerprint
from test_agent_workbench import setup_pair


@pytest.fixture(autouse=True)
def isolated_router(app):
    # This assigned slice can run before main.py is integrated by its owner.
    if importlib.util.find_spec('app.api.companion'):
        from app.api.companion import router
        if '/api/v1/workbench/subjects/{subject_id}/companion/letters' not in app.openapi()['paths']:
            app.include_router(router)
            app.openapi_schema = None
        from app.api import companion
        if hasattr(companion,'spaces_router') and '/api/v1/companion/spaces' not in app.openapi()['paths']:
            app.include_router(companion.spaces_router)
            app.openapi_schema = None


def prepare(app, client, session):
    owner, contributor, oh, ch, ep, _ = setup_pair(app, client, session)
    reader = seed_development_data(session, subject_name='另一空间', actor_name='同名亲友')
    rh = {'Authorization': 'Bearer ' + reader.actor_token}
    root = f'/api/v1/workbench/subjects/{owner.subject_id}/companion'
    return owner, contributor, reader, oh, ch, rh, ep, root


def post(client, path, headers, body, status=200):
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == status, response.text
    return response.json()


def permission(client, root, oh, actor, revision=0, enabled=True):
    response = client.put(root+'/contribution-grants/'+actor.actor_id, headers=oh,
                          json={'revision':revision,'enabled':enabled})
    assert response.status_code == 200, response.text
    return response.json()


def note(client, root, ch, key='note-1'):
    return post(client, root+'/contributions', ch,
                {'idempotency_key':key,'classification':'firsthand','text':'这是亲友亲历的补记。'}, 201)


def share_story(client, root, oh, actor, ep):
    return post(client, root.removesuffix('/companion')+'/grants', oh,
        {'episode_id':ep,'reader_actor_id':actor.actor_id,'include_audio_confirmed':True}, 201)


def test_read_and_contribute_are_independent_with_crosssubject_denial(app,client,session):
    owner,c,r,oh,ch,rh,ep,root = prepare(app,client,session)
    share_story(client,root,oh,r,ep)
    assert client.post(root+'/contributions',headers=rh,json={
        'idempotency_key':'no','classification':'opinion','text':'有阅读权'}).status_code==404
    assert client.put(root+'/contribution-grants/'+c.actor_id,headers=ch,
        json={'revision':0,'enabled':True}).status_code==404
    permission(client,root,oh,c)
    signed=note(client,root,ch)
    assert signed['author_actor_id']==c.actor_id and signed['source_type']=='THIRD_PARTY'
    assert signed['author_display_name']=='读者'
    assert client.get(root.removesuffix('/companion')+'/stories',headers=ch).status_code==404
    foreign=root.replace(owner.subject_id,r.subject_id)
    assert client.get(foreign+'/contributions/'+signed['id'],headers=oh).status_code==404
    assert client.get(root+'/contribution-grants',headers=rh).json()['items']==[]


def test_pending_private_accept_keeps_author_and_explicit_share(app,client,session):
    owner,c,r,oh,ch,rh,ep,root = prepare(app,client,session)
    permission(client,root,oh,c)
    memory_ids=set(session.scalars(select(MemoryItem.memory_item_id)))
    signed=note(client,root,ch);path=root+'/contributions/'+signed['id']
    assert client.get(path,headers=rh).status_code==404
    assert client.get(root+'/contributions',headers=rh).json()['items']==[]
    accepted=post(client,path+'/review',oh,{'revision':1,'decision':'accepted'})
    assert accepted['author_actor_id']==c.actor_id and accepted['visibility']=='owner_and_author'
    assert client.get(path,headers=rh).status_code==404
    assert client.put(path+'/recipients',headers=ch,json={'revision':2,'recipient_actor_ids':[r.actor_id]}).status_code==404
    shared=client.put(path+'/recipients',headers=oh,json={'revision':2,'recipient_actor_ids':[r.actor_id]})
    assert shared.status_code==200,shared.text
    assert client.get(path,headers=rh).json()['author_actor_id']==c.actor_id
    assert client.post(path+'/review',headers=ch,json={'revision':3,'decision':'accepted'}).status_code==404
    assert set(session.scalars(select(MemoryItem.memory_item_id)))==memory_ids
    assert list(session.scalars(select(ProfileCandidate)))==[]
    assert client.post(root+'/contributions',headers=ch,json={
        'idempotency_key':'fake','classification':'opinion','text':'伪署名','author_actor_id':owner.actor_id}).status_code==422


def test_revoke_blocks_new_notes_withdraw_hides_old_text_and_idempotency(app,client,session):
    _,c,r,oh,ch,rh,_,root=prepare(app,client,session)
    permission(client,root,oh,c);signed=note(client,root,ch);path=root+'/contributions/'+signed['id']
    assert note(client,root,ch)['id']==signed['id']
    assert client.post(root+'/contributions',headers=ch,json={
        'idempotency_key':'note-1','classification':'reported','text':'不同'}).status_code==409
    post(client,path+'/review',oh,{'revision':1,'decision':'disagreement'})
    assert client.put(path+'/recipients',headers=oh,json={'revision':2,'recipient_actor_ids':[r.actor_id]}).status_code==200
    permission(client,root,oh,c,revision=1,enabled=False)
    assert client.post(root+'/contributions',headers=ch,json={
        'idempotency_key':'note-2','classification':'opinion','text':'新记录'}).status_code==404
    assert client.get(path,headers=rh).status_code==200
    assert client.post(path+'/withdraw',headers=rh,json={'revision':3}).status_code==404
    withdrawn=post(client,path+'/withdraw',ch,{'revision':3})
    assert withdrawn['status']=='withdrawn' and 'text' not in withdrawn
    assert post(client,path+'/withdraw',ch,{'revision':3})['revision']==4
    assert client.get(path,headers=rh).status_code==404
    assert 'text' not in client.get(path,headers=oh).json()
    assert client.post(path+'/review',headers=oh,json={'revision':4,'decision':'accepted'}).status_code==409


def test_letters_exact_recipient_confirmation_cas_and_terminal_revoke(app,client,session):
    owner,c,r,oh,ch,rh,_,root=prepare(app,client,session)
    body={'idempotency_key':'letter-1','recipient_actor_id':c.actor_id,'title':'给你','text':'只给这个账号。'}
    assert client.post(root+'/letters',headers=ch,json=body).status_code==404
    row=post(client,root+'/letters',oh,body,201);path=root+'/letters/'+row['id']
    assert client.get(path,headers=ch).status_code==404
    assert client.get(root+'/letters',headers=ch).json()['items']==[]
    assert client.post(path+'/publish',headers=oh,json={'revision':1,'confirmed':False}).status_code==422
    published=post(client,path+'/publish',oh,{'revision':1,'confirmed':True})
    assert published['recipient_actor_id']==c.actor_id and published['source_type']=='SUBJECT'
    assert post(client,path+'/publish',oh,{'revision':1,'confirmed':True})['revision']==2
    assert client.get(path,headers=ch).json()['text']==body['text']
    assert client.get(path,headers=rh).status_code==404
    assert client.post(path+'/revoke',headers=oh,json={'revision':1}).status_code==409
    assert client.put(path,headers=oh,json={k:v for k,v in body.items() if k!='idempotency_key'}|{'revision':2}).status_code==409
    post(client,path+'/revoke',oh,{'revision':2})
    assert client.get(path,headers=ch).status_code==404
    assert client.get(root+'/letters',headers=ch).json()['items']==[]
    assert client.post(path+'/publish',headers=oh,json={'revision':3,'confirmed':True}).status_code==409
    assert client.post(root+'/letters',headers=oh,json=body|{'idempotency_key':'fake','recipient_actor_id':'missing'}).status_code==422
    assert client.post(root+'/letters',headers=oh,json=body|{'audio_episode_id':'ignored'}).status_code==422


def selected(app,client,session):
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    sources=material_map(session,owner.subject_id,owner.actor_id);session.commit()
    evidence=next(iter(sources))
    record=post(client,root.removesuffix('/companion')+'/narrative/records',oh,
        {'kind':'story','title':'选中的故事','text':'审核的经历','evidence_ids':[evidence],
         'facets':['EXPERIENCE']},201)
    post(client,root.removesuffix('/companion')+'/narrative/records/'+record['id']+'/confirm',oh,{'revision':1})
    grant=share_story(client,root,oh,c,ep)
    selection={'narrative_ids':[record['id']],'profile_candidate_ids':[],'recipient_actor_ids':[c.actor_id]}
    preview=post(client,root+'/snapshots/preview',oh,selection)
    body=selection|{'idempotency_key':'snapshot-1','source_version':preview['source_version'],'confirmed':True}
    return owner,c,r,oh,ch,rh,ep,root,record,grant,body


def test_snapshot_immutable_source_grants_live_and_owner_historical_metadata(app,client,session):
    owner,c,r,oh,ch,rh,ep,root,record,grant,body=selected(app,client,session)
    row=post(client,root+'/snapshots',oh,body,201);path=root+'/snapshots/'+row['id']
    assert post(client,root+'/snapshots',oh,body,201)['id']==row['id']
    assert row['readonly'] is True and row['items'][0]['content']['text']=='审核的经历'
    assert client.get(path,headers=rh).status_code==404
    assert client.get(path.replace(owner.subject_id,r.subject_id),headers=rh).status_code==404
    assert client.put(path,headers=oh,json={'text':'改写'}).status_code==405
    assert client.get(path,headers=ch).json()['items'][0]['content']==row['items'][0]['content']
    assert client.delete(root.removesuffix('/companion')+'/grants/'+grant['grant_id'],headers=oh).status_code==200
    assert client.get(path,headers=ch).status_code==404
    assert client.get(path,headers=oh).json()['items'][0]['source_valid'] is True
    session.expire_all();session.get(Episode,ep).transcript='来源已变';session.commit()
    historical=client.get(path,headers=oh).json()
    assert historical['items'][0]['source_valid'] is False and 'content' not in historical['items'][0]
    from app.companion_models import SealedSnapshot
    session.expire_all();stored=session.get(SealedSnapshot,row['id'])
    assert stored.items[0]['content']==row['items'][0]['content']


def test_snapshot_create_source_cas_and_no_new_read_grants(app,client,session):
    owner,c,r,oh,ch,rh,ep,root,record,grant,body=selected(app,client,session)
    assert client.post(root+'/snapshots',headers=ch,json=body).status_code==404
    assert client.post(root+'/snapshots/preview',headers=oh,json={
        'narrative_ids':[record['id']],'recipient_actor_ids':[r.actor_id]}).status_code==404
    assert client.post(root+'/snapshots',headers=oh,json=body|{'confirmed':False}).status_code==422
    session.expire_all();session.get(NarrativeRecord,record['id']).revision+=1;session.commit()
    assert client.post(root+'/snapshots',headers=oh,json=body).status_code==409
    assert client.post(root+'/snapshots/preview',headers=oh,json={'narrative_ids':['foreign']}).status_code==404


def test_snapshot_selected_profile_checks_basis_and_counter_sources(app,client,session):
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    sources=material_map(session,owner.subject_id,owner.actor_id)
    eid=next(iter(sources));basis=profile_source_basis(session,owner.subject_id)
    candidate=ProfileCandidate(candidate_id='confirmed-profile',subject_id=owner.subject_id,
        domain='VALUES',kind='trait',statement='确认的有条件观察',context='仅此情境',
        evidence_ids=[eid],counter_evidence_ids=[],independent_episodes=1,source_basis=basis,
        status='pending',model_version='fixture',prompt_version='fixture')
    session.add(candidate);session.commit()
    confirmed=client.post(root.removesuffix('/companion')+'/profile-candidates/'+candidate.candidate_id+'/confirm',headers=oh)
    assert confirmed.status_code==200,confirmed.text
    share_story(client,root,oh,c,ep)
    selection={'profile_candidate_ids':[candidate.candidate_id],'recipient_actor_ids':[c.actor_id]}
    preview=post(client,root+'/snapshots/preview',oh,selection)
    row=post(client,root+'/snapshots',oh,selection|{'idempotency_key':'p','confirmed':True,'source_version':preview['source_version']},201)
    path=root+'/snapshots/'+row['id']
    assert client.get(path,headers=ch).json()['items'][0]['content']['context']=='仅此情境'
    session.expire_all();session.get(ProfileCandidate,candidate.candidate_id).status='rejected';session.commit()
    assert client.get(path,headers=ch).status_code==404
    assert 'content' not in client.get(path,headers=oh).json()['items'][0]


def test_draft_edit_recipient_and_crosssubject_links(app,client,session):
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    body={'idempotency_key':'draft','recipient_actor_id':c.actor_id,'title':'草稿','text':'旧文字'}
    row=post(client,root+'/letters',oh,body,201);path=root+'/letters/'+row['id']
    edited={'revision':1,'recipient_actor_id':r.actor_id,'title':'核对后','text':'新文字'}
    response=client.put(path,headers=oh,json=edited)
    assert response.status_code==200,response.text
    assert response.json()['revision']==2
    assert client.put(path,headers=oh,json=edited).json()['revision']==2
    assert client.put(path,headers=oh,json=edited|{'text':'并发变化'}).status_code==409
    post(client,path+'/publish',oh,{'revision':2,'confirmed':True})
    assert client.get(path,headers=ch).status_code==404
    assert client.get(path,headers=rh).json()['text']=='新文字'
    assert client.get(path.replace(owner.subject_id,r.subject_id),headers=rh).status_code==404
    assert client.get(root.removesuffix('/companion')+'/stories',headers=rh).status_code==404
    permission(client,root,oh,c)
    assert client.put(root+'/contribution-grants/'+c.actor_id,headers=oh,
        json={'revision':0,'enabled':False}).status_code==409


def test_snapshot_filters_one_stale_item_preserves_other_and_sealed_storage(app,client,session):
    owner,c,r,oh,ch,rh,ep,root,record,grant,body=selected(app,client,session)
    sources=material_map(session,owner.subject_id,owner.actor_id);session.commit()
    second=post(client,root.removesuffix('/companion')+'/narrative/records',oh,
        {'kind':'observation','title':'第二条','text':'仍有效的观察','evidence_ids':[next(iter(sources))],
         'facets':['EXPERIENCE']},201)
    second_path=root.removesuffix('/companion')+'/narrative/records/'+second['id']
    post(client,second_path+'/confirm',oh,{'revision':1})
    selection={'narrative_ids':[record['id'],second['id']],'recipient_actor_ids':[c.actor_id]}
    preview=post(client,root+'/snapshots/preview',oh,selection)
    row=post(client,root+'/snapshots',oh,selection|{'idempotency_key':'two','source_version':preview['source_version'],'confirmed':True},201)
    path=root+'/snapshots/'+row['id']
    assert len(client.get(path,headers=ch).json()['items'])==2
    # Later organization never mutates sealed payloads. Changed selected status
    # removes only that item from recipient projection, keeping valid sources.
    post(client,second_path+'/reject',oh,{'revision':2})
    recipient=client.get(path,headers=ch).json()
    assert [i['source_id'] for i in recipient['items']]==[record['id']]
    assert len(client.get(path,headers=oh).json()['items'])==2
    assert 'content' not in client.get(path,headers=oh).json()['items'][1]
    post(client,path+'/revoke',oh,{'revision':1})
    assert client.get(path,headers=ch).status_code==404
    assert all('content' not in item for item in client.get(path,headers=oh).json()['items'])
    from app.companion_models import SealedSnapshot
    session.expire_all()
    assert len(session.get(SealedSnapshot,row['id']).items)==2


def test_deleted_memory_invalidates_snapshot_and_owner_metadata_no_text(app,client,session):
    _,c,_,oh,ch,_,ep,root,record,grant,body=selected(app,client,session)
    row=post(client,root+'/snapshots',oh,body,201);path=root+'/snapshots/'+row['id']
    session.expire_all()
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    memory.deleted_at=utcnow();session.commit()
    assert client.get(path,headers=ch).status_code==404
    assert client.get(root+'/snapshots',headers=ch).json()['items']==[]
    history=client.get(path,headers=oh).json()
    assert history['source_valid'] is False and 'content' not in history['items'][0]


def test_additive_migration_sqlite_roundtrip_and_postgres_ddl(tmp_path):
    import io
    from alembic import command
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect
    from conftest import alembic_config, BACKEND_ROOT
    from app.companion_models import ContributionGrant, CompanionContribution, CompanionLetter, SealedSnapshot
    url='sqlite:///'+str(tmp_path/'migration.db')
    config=alembic_config(url);command.upgrade(config,'head')
    engine=create_engine(url)
    try:
        for model in (ContributionGrant,CompanionContribution,CompanionLetter,SealedSnapshot):
            assert {c['name'] for c in inspect(engine).get_columns(model.__tablename__)}==set(model.__table__.columns.keys())
        command.downgrade(config,'0016_share_invitations')
        assert 'companion_letters' not in inspect(engine).get_table_names()
        assert 'share_invitations' in inspect(engine).get_table_names()
        command.upgrade(config,'head')
        assert 'sealed_snapshots' in inspect(engine).get_table_names()
    finally: engine.dispose()
    # Compile only this additive migration for PostgreSQL. This does not claim
    # a live PostgreSQL database executed upgrade/downgrade.
    spec=importlib.util.spec_from_file_location('companion_migration',BACKEND_ROOT/'migrations/versions/0017_companion.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sql=io.StringIO()
    context=MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':sql})
    with Operations.context(context):
        module.upgrade();module.downgrade()
    assert 'CREATE TABLE companion_letters' in sql.getvalue()
    assert 'DROP TABLE sealed_snapshots' in sql.getvalue()


def test_discovery_uses_side_access_without_expanding_story_permissions(app,client,session):
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    path='/api/v1/companion/spaces'
    assert client.get(path).status_code==401
    response=client.get(path,headers=ch)
    assert response.status_code==200,response.text
    assert owner.subject_id not in {item['subject_id'] for item in response.json()['items']}
    permission(client,root,oh,c)
    found=client.get(path,headers=ch).json()['items']
    assert found==[{'subject_id':owner.subject_id,'display_name':'记录者','role':'companion'}]
    assert client.get(root.removesuffix('/companion')+'/stories',headers=ch).status_code==404
    signed=note(client,root,ch);note_path=root+'/contributions/'+signed['id']
    post(client,note_path+'/review',oh,{'revision':1,'decision':'accepted'})
    assert client.put(note_path+'/recipients',headers=oh,json={'revision':2,'recipient_actor_ids':[r.actor_id]}).status_code==200
    assert owner.subject_id in {item['subject_id'] for item in client.get(path,headers=rh).json()['items']}
    post(client,note_path+'/withdraw',ch,{'revision':3})
    assert client.get(path,headers=rh).json()['items']==[]
    permission(client,root,oh,c,revision=1,enabled=False)
    assert client.get(path,headers=ch).json()['items']==[]
    letter=post(client,root+'/letters',oh,{'idempotency_key':'discover','recipient_actor_id':c.actor_id,
        'title':'私信','text':'指定账号'},201)
    assert client.get(path,headers=ch).json()['items']==[]
    letter_path=root+'/letters/'+letter['id']
    post(client,letter_path+'/publish',oh,{'revision':1,'confirmed':True})
    assert client.get(path,headers=ch).json()['items'][0]['subject_id']==owner.subject_id
    assert client.get(root.removesuffix('/companion')+'/stories',headers=ch).status_code==404
    post(client,letter_path+'/revoke',oh,{'revision':2})
    assert client.get(path,headers=ch).json()['items']==[]


def test_snapshot_discovery_requires_live_source_authorization(app,client,session):
    owner,c,r,oh,ch,rh,ep,root,record,grant,body=selected(app,client,session)
    path='/api/v1/companion/spaces'
    assert client.get(path,headers=ch).status_code==200
    assert client.get(path,headers=ch).json()['items']==[]  # StoryGrant alone is another discovery surface.
    row=post(client,root+'/snapshots',oh,body,201)
    assert client.get(path,headers=ch).json()['items'][0]['subject_id']==owner.subject_id
    assert client.get(path,headers=rh).json()['items']==[]
    client.delete(root.removesuffix('/companion')+'/grants/'+grant['grant_id'],headers=oh)
    assert client.get(path,headers=ch).json()['items']==[]


@pytest.mark.parametrize('confirm_via_update',[False,True])
@pytest.mark.parametrize('mutation',['source','revoke'])
def test_real_profile_confirmation_can_seal_and_live_changes_hide_content(app,client,session,confirm_via_update,mutation):
    from app.materials import effective_materials
    from app.profile_updates import evidence_fingerprint
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    raw=effective_materials(session,owner.subject_id,{ep})[0]['evidence'][0]
    session.commit()
    candidate=ProfileCandidate(candidate_id='real-confirm',subject_id=owner.subject_id,
        domain='PREFERENCES',kind='habit',statement='真实接口确认的情境观察',context='仅在讲述所述情境',
        evidence_ids=[raw['evidence_id']],counter_evidence_ids=[],independent_episodes=1,
        source_basis=profile_source_basis(session,owner.subject_id),status='pending',
        model_version='fixture',prompt_version='fixture')
    session.add(candidate);session.commit()
    profiles=root.removesuffix('/companion')+'/profile-candidates'
    if confirm_via_update:
        update=post(client,profiles+'/updates',oh,{'candidate_id':candidate.candidate_id,
            'action':'ADD','reason':'本人逐条核对后接受'},201)
        confirmed=client.post(profiles+'/updates/'+update['update_id']+'/confirm',headers=oh)
    else:
        confirmed=client.post(profiles+'/'+candidate.candidate_id+'/confirm',headers=oh)
    assert confirmed.status_code==200,confirmed.text
    session.expire_all()
    saved=session.get(ProfileCandidate,candidate.candidate_id)
    assert saved.evidence_snapshot=={raw['evidence_id']:evidence_fingerprint(raw)}
    # The narrative context field must never silently change the profile protocol.
    contextual=material_map(session,owner.subject_id,owner.actor_id)[raw['evidence_id']]
    assert fingerprint(contextual)!=evidence_fingerprint(raw)
    session.commit()
    grant=share_story(client,root,oh,c,ep)
    selection={'profile_candidate_ids':[candidate.candidate_id],'recipient_actor_ids':[c.actor_id]}
    preview=post(client,root+'/snapshots/preview',oh,selection)
    assert preview['items'][0]['content']['statement']==candidate.statement
    row=post(client,root+'/snapshots',oh,selection|{'idempotency_key':'real-profile',
        'source_version':preview['source_version'],'confirmed':True},201)
    path=root+'/snapshots/'+row['id']
    assert client.get(path,headers=ch).json()['items'][0]['content']['statement']==candidate.statement
    if mutation=='revoke':
        assert client.delete(root.removesuffix('/companion')+'/grants/'+grant['grant_id'],headers=oh).status_code==200
        assert client.get(path,headers=oh).json()['items'][0]['source_valid'] is True
    else:
        session.expire_all();session.get(Episode,ep).transcript+='。后来资料有新变化';session.commit()
        historical=client.get(path,headers=oh).json()['items'][0]
        assert historical['source_valid'] is False and 'content' not in historical
    assert client.get(path,headers=ch).status_code==404


def test_snapshot_narrative_requires_recipient_context_fingerprint_not_only_source_id(app,client,session):
    from app.models import MemoryRevision
    from test_twin_voice import _record
    owner,c,r,oh,ch,rh,ep,root=prepare(app,client,session)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.get(Episode,ep).idempotency_key+='-first';session.commit()
    private=_record(client,app,owner.subject_id,owner.consent_id,oh)
    session.add(MemoryRevision(revision_id='snapshot-private-context',subject_id=owner.subject_id,
        target_memory_id=old.memory_item_id,episode_id=private,kind='change',status='confirmed',
        time_text='私人日期2039年3月2日'));session.commit()
    owner_sources=material_map(session,owner.subject_id,owner.actor_id);session.commit()
    eid=old.evidence_ids[0]
    assert '私人日期' in owner_sources[eid]['temporal_context']
    narrative=root.removesuffix('/companion')+'/narrative'
    record=post(client,narrative+'/records',oh,{'kind':'observation','title':'带变化背景的理解',
        'text':'这段历史后来发生变化，私人日期2039年3月2日。','evidence_ids':[eid],
        'facets':['EXPERIENCE']},201)
    post(client,narrative+'/records/'+record['id']+'/confirm',oh,{'revision':1})
    share_story(client,root,oh,c,ep)
    private_grant=share_story(client,root,oh,c,private)
    selection={'narrative_ids':[record['id']],'recipient_actor_ids':[c.actor_id]}
    preview=post(client,root+'/snapshots/preview',oh,selection)
    row=post(client,root+'/snapshots',oh,selection|{'idempotency_key':'private-context',
        'source_version':preview['source_version'],'confirmed':True},201)
    path=root+'/snapshots/'+row['id']
    assert client.get(path,headers=ch).status_code==200
    assert client.delete(root.removesuffix('/companion')+'/grants/'+private_grant['grant_id'],headers=oh).status_code==200
    reader_sources=material_map(session,owner.subject_id,c.actor_id);session.commit()
    assert eid in reader_sources and fingerprint(reader_sources[eid])!=fingerprint(owner_sources[eid])
    ordinary=client.get(narrative,headers=ch)
    assert ordinary.status_code==200 and ordinary.json()['records']==[]
    assert '私人日期' not in ordinary.text
    assert client.post(root+'/snapshots/preview',headers=oh,json=selection).status_code==404
    assert client.get(path,headers=ch).status_code==404
    assert client.get(root+'/snapshots',headers=ch).json()['items']==[]
    assert client.get(path,headers=oh).json()['items'][0]['source_valid'] is True
