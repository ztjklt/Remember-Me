"""A lost result acknowledgement must not erase an otherwise valid candidate."""
from sqlalchemy import select
from app.learning_models import PersonalTrainingJob
from test_personal_learning_api import learning_owner, _claimed_job, _result_payload, _worker_headers

def test_trained_result_ack_is_idempotent_and_late_heartbeat_does_not_revoke(learning_owner,client,app,session):
    job=_claimed_job(client,app,session,learning_owner)
    payload=_result_payload(job)
    result={**payload['result'],'status':'trained','reason':'synthetic_test', 'adapter_sha256':'a'*64,
        'metrics':dict(baseline_validation_loss=1.,validation_loss=.8,baseline_test_loss=1.,test_loss=.8,
            weight_delta_l2=.1,optimizer_steps=job['policy']['iterations'],trainable_parameter_count=100,
            peak_memory_bytes=1000,mlx_lm_version='synthetic-test')}
    body={**payload,'result':result};path='/internal/personal-learning/jobs/'+job['job_id']
    first=client.post(path+'/result',headers=_worker_headers(),json=body)
    repeat=client.post(path+'/result',headers=_worker_headers(),json=body)
    assert first.status_code==repeat.status_code==200
    assert first.json()==repeat.json()=={'status':'awaiting_validation','activation_allowed':False}
    assert client.post(path+'/heartbeat',headers=_worker_headers(),json={k:body[k] for k in ['worker_id','lease_token']}).status_code==409
    session.expire_all()
    assert session.get(PersonalTrainingJob,job['job_id']).status=='awaiting_validation'
