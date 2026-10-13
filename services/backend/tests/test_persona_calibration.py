from sqlalchemy import select
from app.models import CalibrationRun
from app.seed import seed_development_data
from test_twin_voice import _record, QuoteTwin


def test_cannot_start_new_calibration_with_answer_whose_context_changed(app, client, session):
    own = seed_development_data(session, subject_name='Own', actor_name='Own')
    reader = seed_development_data(session, subject_name='Other', actor_name='Other')
    headers = {'Authorization': 'Bearer '+own.actor_token}
    _record(client, app, own.subject_id, own.consent_id, headers)
    app.state.settings.ai_backend='http'; app.state.twin_client=QuoteTwin()
    cloud=client.post('/api/v1/consents',headers=headers,json={
        'subject_id':own.subject_id,'scope':'CLOUD_TWIN'}).json()['consent_id']
    path=f'/api/v1/subjects/{own.subject_id}'
    answer=client.post(path+'/twin/answers',headers=headers,json={
        'question':'喜欢什么？','cloud_consent_id':cloud}).json()
    # Changing the allowed companion context changes the generation basis,
    # without eagerly marking the saved answer invalidated_at.
    grant=client.put(f'/api/v1/workbench/subjects/{own.subject_id}/companion/contribution-grants/{reader.actor_id}',
        headers=headers,json={'revision':0,'enabled':True})
    assert grant.status_code==200,grant.text
    locked=client.post(path+'/calibrations',headers=headers,json={
        'twin_answer_id':answer['answer_id'],'cloud_consent_id':cloud})
    assert locked.status_code==409,locked.text
    assert list(session.scalars(select(CalibrationRun)))==[]
