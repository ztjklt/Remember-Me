from sqlalchemy import select
from app.models import ProfileCandidate, ProfileRefresh, ProfileUpdate, Episode
from app.profiles import run_profile_once
import pytest
from test_profile_updates import prepare


class Relations:
    def propose_relations(self,payload):
        new=payload['candidates'][0]; old=payload['targets'][0]
        return {'relations':[{'candidate_id':new['candidate_id'],'target_candidate_id':old['candidate_id'],
            'action':'CONFLICT','reason':'两条理解需要本人核对','time_text':'','time_evidence_id':None,
            'evidence_ids':list(dict.fromkeys(new['evidence_ids']+old['evidence_ids']))}],
            'model_version':'test-model','prompt_version':'profile-relations-v1'}


def test_relation_job_requires_owner_and_only_creates_pending_update(app,client,session):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    body={'cloud_consent_id':cloud}
    assert client.post(root+'/suggest-relations',headers=rh,json=body).status_code==404
    response=client.post(root+'/suggest-relations',headers=oh,json=body)
    assert response.status_code==202,response.text
    job=response.json()['job_id']
    assert client.post(root+'/suggest-relations',headers=oh,json=body).json()['job_id']==job
    run_profile_once(app.state.database,Relations())
    session.expire_all()
    assert session.get(ProfileRefresh,job).status=='complete'
    rows=list(session.scalars(select(ProfileUpdate)))
    assert len(rows)==1 and rows[0].status=='pending' and rows[0].origin=='model'
    assert session.get(ProfileCandidate,'target').status=='confirmed'
    view=client.get(root+'/updates',headers=oh).json()['items'][0]
    assert view['model_version']=='test-model' and view['prompt_version']=='profile-relations-v1'
    # Same source/version request cannot publish duplicates.
    client.post(root+'/suggest-relations',headers=oh,json=body)
    run_profile_once(app.state.database,Relations())
    assert len(client.get(root+'/updates',headers=oh).json()['items'])==1


def test_relation_result_discarded_if_source_changes_during_model_call(app,client,session):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    response=client.post(root+'/suggest-relations',headers=oh,json={'cloud_consent_id':cloud})
    assert response.status_code==202,response.text
    class Changed(Relations):
        def propose_relations(self,payload):
            # A real independent transaction during the unlocked network stage.
            with app.state.database.session() as other:
                other.get(Episode,ep).transcript+='。来源有变化';other.commit()
            return super().propose_relations(payload)
    run_profile_once(app.state.database,Changed())
    session.expire_all()
    assert session.get(ProfileRefresh,response.json()['job_id']).status=='failed'
    assert not list(session.scalars(select(ProfileUpdate)))


@pytest.mark.parametrize('change', ['target', 'consent'])
def test_relation_publication_rechecks_consent_and_target(app,client,session,change):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    job=client.post(root+'/suggest-relations',headers=oh,json={'cloud_consent_id':cloud}).json()['job_id']
    class Changed(Relations):
        def propose_relations(self,payload):
            with app.state.database.session() as other:
                if change=='target': other.get(ProfileCandidate,'target').status='rejected'
                else:
                    from app.models import Consent
                    other.get(Consent,cloud).status='revoked'
                other.commit()
            return super().propose_relations(payload)
    run_profile_once(app.state.database,Changed())
    session.expire_all()
    assert session.get(ProfileRefresh,job).status=='failed'
    assert not list(session.scalars(select(ProfileUpdate)))


@pytest.mark.parametrize('bad', ['foreign_target','foreign_source','fabricated_time','duplicate_support'])
def test_backend_rejects_invalid_model_relationships(app,client,session,bad):
    owner,oh,rh,ep,cloud,root=prepare(app,client,session)
    job=client.post(root+'/suggest-relations',headers=oh,json={'cloud_consent_id':cloud}).json()['job_id']
    class Invalid(Relations):
        def propose_relations(self,payload):
            output=super().propose_relations(payload);r=output['relations'][0]
            if bad=='foreign_target': r['target_candidate_id']='another-space'
            if bad=='foreign_source': r['evidence_ids'].append('private-foreign-source')
            if bad=='fabricated_time': r.update(action='CHANGE',time_text='不在原文的时间',time_evidence_id=r['evidence_ids'][0])
            if bad=='duplicate_support': r['action']='SUPPORT'
            return output
    run_profile_once(app.state.database,Invalid())
    session.expire_all()
    assert session.get(ProfileRefresh,job).status=='failed'
    assert not list(session.scalars(select(ProfileUpdate)))
    assert session.get(ProfileCandidate,'target').status=='confirmed'
