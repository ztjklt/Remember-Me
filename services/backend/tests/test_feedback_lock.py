"""Calibration must freeze exactly the effective displayed wording, not learn its own text."""
import pytest
from app.models import TwinAnswer
from test_agent_workbench import setup_pair


@pytest.mark.parametrize('kind,status,text,expected', [
    ('SIMULATION','available','根据记录，他会先安静一会儿，再做决定。','根据记录，他会先安静一会儿，再做决定。'),
    ('SIMULATION','rejected','不应显示的文字','我喜欢散步'),
    ('SIMULATION','available','   ','我喜欢散步'),
    ('ORIGINAL','available','不应改写原话','我喜欢散步'),
])
def test_feedback_freezes_displayed_answer_and_never_changes_source(app,client,session,kind,status,text,expected):
    owner,reader,oh,rh,ep,cloud=setup_pair(app,client,session)
    answer=client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'我喜欢什么？','cloud_consent_id':cloud}).json()
    row=session.get(TwinAnswer,answer['answer_id']);row.response_type=kind
    row.expression={'status':status,'text':text,'model_version':'checked-style-test','prompt_version':'expression-checked-v1'}
    session.commit()
    path=f'/api/v1/subjects/{owner.subject_id}/calibrations'
    locked=client.post(path,headers=oh,json={'twin_answer_id':row.answer_id,'cloud_consent_id':cloud})
    assert locked.status_code==200,locked.text
    assert locked.json()['locked_answer']==expected
    assert locked.json()['locked_model_version']==('checked-style-test' if expected==text else row.model_version)
    # Later display changes cannot rewrite the already locked prediction.
    row.expression={**row.expression,'text':'后来的回答'};session.commit()
    assert client.post(path,headers=oh,json={'twin_answer_id':row.answer_id,'cloud_consent_id':cloud}).json()['locked_answer']==expected
    assert client.post(path+'/'+locked.json()['calibration_id']+'/complete',headers=oh,
        json={'cloud_consent_id':cloud}).status_code==409
    session.expire_all();assert session.get(TwinAnswer,row.answer_id).answer=='我喜欢散步'
