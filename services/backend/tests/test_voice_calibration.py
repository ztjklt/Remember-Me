from test_persona_contribution_limits import setup


def test_blind_prepare_and_list_do_not_disclose_locked_answer(app,client,session):
    owner,oh,ah,root,consent,spy=setup(app,client,session)
    path=f'/api/v1/subjects/{owner.subject_id}/calibrations'
    body=dict(question='会怎么考虑？',mode='persona',cloud_consent_id=consent)
    # Use full source selection via a deterministic encoder stub fixture already
    # provided by prepare; the question remains a request, not a stored memory.
    response=client.post(path+'/prepare-voice',headers=oh,json=body)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['status']=='awaiting_human' and result['answer_hidden']
    assert result['locked_answer'] is None
    answer_path=f'/api/v1/subjects/{owner.subject_id}/twin/answers/'+result['twin_answer_id']
    assert client.get(answer_path,headers=oh).status_code==404
    assert client.post(answer_path+'/speech',headers=oh).status_code==404
    assert client.get(path,headers=oh).json()['items'][0]['locked_answer'] is None
    assert client.post(path+'/prepare-voice',headers=ah,json=body).status_code==404
