"""Confirmed owner understanding projection; no reader recomputation or providers."""
import pytest
from sqlalchemy import select
from app.models import ProfileCandidate, Episode, MemoryItem, MemoryRevision
from app.access import profile_source_basis
from app.materials import effective_materials
from app.narrative import material_map
from test_agent_workbench import setup_pair
from test_twin_voice import _record


def prepare(app,client,session,second=False):
    owner,reader,oh,rh,ep,_=setup_pair(app,client,session)
    other=None
    if second:
        session.get(Episode,ep).idempotency_key+='-first';session.commit()
        other=_record(client,app,owner.subject_id,owner.consent_id,oh)
    sources=material_map(session,owner.subject_id,owner.actor_id);session.commit()
    old=next(e for e in sources.values() if e['episode_id']==ep)
    extra=next((e for e in sources.values() if e['episode_id']==other),None)
    root=f'/api/v1/workbench/subjects/{owner.subject_id}'
    return owner,reader,oh,rh,ep,other,old,extra,root


def grant(client,root,oh,reader,ep):
    r=client.post(root+'/grants',headers=oh,json={'episode_id':ep,
        'reader_actor_id':reader.actor_id,'include_audio_confirmed':True})
    assert r.status_code==201,r.text
    return r.json()


def candidate(session,owner,support,counter=(),id='reader-confirmed',context='仅在所述生活情境'):
    row=ProfileCandidate(candidate_id=id,subject_id=owner.subject_id,domain='PREFERENCES',
        kind='habit',statement='本人确认的节俭理解'+id,context=context,
        evidence_ids=[e['evidence_id'] for e in support],counter_evidence_ids=[e['evidence_id'] for e in counter],
        independent_episodes=1,source_basis=profile_source_basis(session,owner.subject_id),status='pending',
        model_version='fixture',prompt_version='fixture')
    session.add(row);session.commit()
    return row


def confirm(client,root,oh,row):
    r=client.post(root+'/profile-candidates/'+row.candidate_id+'/confirm',headers=oh)
    assert r.status_code==200,r.text


def projection(client,root,rh):
    r=client.get(root+'/narrative',headers=rh)
    assert r.status_code==200,r.text
    return r


def test_real_confirmation_is_projected_but_pending_private_candidates_are_not(app,client,session):
    owner,reader,oh,rh,ep,_,source,_,root=prepare(app,client,session)
    row=candidate(session,owner,[source])
    private=candidate(session,owner,[source],id='PRIVATE_PENDING_CANDIDATE')
    grant(client,root,oh,reader,ep)
    assert projection(client,root,rh).json()['understandings']==[]
    confirm(client,root,oh,row)
    response=projection(client,root,rh)
    items=response.json()['understandings']
    assert len(items)==1 and items[0]['candidate_id']==row.candidate_id
    assert items[0]['statement']==row.statement and items[0]['context']==row.context
    assert items[0]['status']=='confirmed' and items[0]['source_valid'] is True
    assert items[0]['scope']=='shared_confirmed' and items[0]['reader_recomputed'] is False
    assert items[0]['evidence_ids']==[source['evidence_id']]
    assert 'PRIVATE_PENDING_CANDIDATE' not in response.text
    assert response.json()['next_question'] is None
    assert client.get(root+'/profile-candidates',headers=rh).status_code==404


@pytest.mark.parametrize('missing_role',['support','counter'])
def test_all_support_and_counter_sources_required_without_partial_summary_leak(app,client,session,missing_role):
    owner,reader,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    row=candidate(session,owner,[source],[extra],id='PRIVATE_PARTIAL_SUMMARY')
    confirm(client,root,oh,row)
    grant(client,root,oh,reader,other if missing_role=='support' else ep)
    response=projection(client,root,rh)
    assert response.json()['understandings']==[] and row.candidate_id not in response.text
    hidden=source if missing_role=='support' else extra
    assert hidden['evidence_id'] not in response.text and hidden['episode_id'] not in response.text
    grant(client,root,oh,reader,ep if missing_role=='support' else other)
    items=projection(client,root,rh).json()['understandings']
    assert len(items)==1 and items[0]['counter_evidence_ids']==[extra['evidence_id']]


@pytest.mark.parametrize('mutation',['revoke','modify','delete','reject','tamper_saved_fingerprint','empty_saved_snapshot'])
def test_live_source_and_permission_changes_hide_understanding(app,client,session,mutation):
    owner,reader,oh,rh,ep,other,source,extra,root=prepare(app,client,session,second=True)
    row=candidate(session,owner,[source],[extra])
    confirm(client,root,oh,row)
    old_grant=grant(client,root,oh,reader,ep);grant(client,root,oh,reader,other)
    assert len(projection(client,root,rh).json()['understandings'])==1
    if mutation=='revoke':
        assert client.delete(root+'/grants/'+old_grant['grant_id'],headers=oh).status_code==200
    elif mutation=='reject':
        assert client.post(root+'/profile-candidates/'+row.candidate_id+'/reject',headers=oh).status_code==200
    elif mutation=='delete':
        memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
        assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}',headers=oh).status_code==200
    else:
        session.expire_all()
        if mutation=='modify':
            session.get(Episode,ep).transcript+='。新的本人说明'
        else:
            saved=session.get(ProfileCandidate,row.candidate_id)
            if mutation=='empty_saved_snapshot':
                saved.evidence_snapshot={}
            else:
                # Keep the complete key set so this proves value equality,
                # independently from missing-support/counter-source rejection.
                changed=dict(saved.evidence_snapshot);changed[source['evidence_id']]='forged'
                saved.evidence_snapshot=changed
        session.commit()
    response=projection(client,root,rh)
    assert response.json()['understandings']==[] and row.candidate_id not in response.text


def test_crosssubject_evidence_and_wrong_subject_never_project(app,client,session):
    owner,reader,oh,rh,ep,_,source,_,root=prepare(app,client,session)
    foreign=_record(client,app,reader.subject_id,reader.consent_id,rh)
    foreign_source=effective_materials(session,reader.subject_id,{foreign})[0]['evidence'][0]
    session.commit()
    row=candidate(session,owner,[foreign_source],id='CROSS_SUBJECT_PRIVATE')
    assert client.post(root+'/profile-candidates/'+row.candidate_id+'/confirm',headers=oh).status_code==409
    # Even corrupt legacy state must not turn foreign sources into readable facts.
    session.expire_all();bad=session.get(ProfileCandidate,row.candidate_id)
    bad.status='confirmed';bad.evidence_snapshot={foreign_source['evidence_id']:'forged'};session.commit()
    grant(client,root,oh,reader,ep)
    response=projection(client,root,rh)
    assert response.json()['understandings']==[] and row.candidate_id not in response.text
    assert foreign_source['evidence_id'] not in response.text
    assert client.get(root.replace(owner.subject_id,reader.subject_id)+'/narrative',headers=oh).status_code==404


def test_private_change_context_requires_complete_reader_visibility(app,client,session):
    owner,reader,oh,rh,ep,private,source,_,root=prepare(app,client,session,second=True)
    old=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    session.add(MemoryRevision(revision_id='reader-private-change',subject_id=owner.subject_id,
        target_memory_id=old.memory_item_id,episode_id=private,kind='change',status='confirmed',
        time_text='私人变化日期2039年3月2日'));session.commit()
    # Profile confirmation canonically hashes raw evidence. The projected context
    # still cannot carry owner-only temporal dependencies through a readable ID.
    row=candidate(session,owner,[source],id='PRIVATE_CHANGE_UNDERSTANDING',context='私人变化日期2039年3月2日后')
    confirm(client,root,oh,row);grant(client,root,oh,reader,ep)
    response=projection(client,root,rh)
    assert response.json()['understandings']==[] and '私人变化日期' not in response.text
    private_grant=grant(client,root,oh,reader,private)
    assert len(projection(client,root,rh).json()['understandings'])==1
    assert client.delete(root+'/grants/'+private_grant['grant_id'],headers=oh).status_code==200
    assert projection(client,root,rh).json()['understandings']==[]
