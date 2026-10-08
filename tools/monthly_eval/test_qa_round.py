from qa_round import pending_attempts


def test_resume_unfinished_row_but_not_success_or_terminal_failure():
    assert list(pending_attempts({'attempts':[]}))==[0,1,2]
    assert list(pending_attempts({'attempts':[{'error':'timeout'}]}))==[1,2]
    assert list(pending_attempts({'attempts':[],'result':{}}))==[]
    assert list(pending_attempts({'attempts':[],'terminal_error':True}))==[]
    assert list(pending_attempts({'attempts':[{}, {}, {}]}))==[]
