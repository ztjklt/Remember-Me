import pytest
from cloud_followthrough import Steps, wait_profile


def test_restart_skips_completed_qa_and_profile_posts(tmp_path):
    path = tmp_path / 'steps.json'
    calls = []
    first = Steps(path)
    assert first.once('qa/owner', lambda: calls.append('qa') or {'answer_id': 'a'}) == {'answer_id': 'a'}
    first.once('profile/job', lambda: calls.append('profile') or {'job_id': 'j'})
    # A wait timeout must not erase the successfully queued job or Twin answer.
    with pytest.raises(RuntimeError, match='still pending'):
        wait_profile(lambda: {'jobs': [{'job_id': 'j', 'status': 'pending'}]}, 'j', seconds=0)
    restarted = Steps(path)
    restarted.once('qa/owner', lambda: pytest.fail('duplicate QA'))
    job = restarted.once('profile/job', lambda: pytest.fail('duplicate profile refresh'))
    result = wait_profile(lambda: {'jobs': [{'job_id': job['job_id'], 'status': 'complete'}], 'items': [{'id': 'p'}]}, 'j', seconds=0)
    assert result['items']
    assert calls == ['qa', 'profile']


def test_ambiguous_post_is_not_automatically_replayed(tmp_path):
    path = tmp_path / 'steps.json'
    calls = []
    def lost_response():
        calls.append('submitted')
        raise TimeoutError('lost response')
    with pytest.raises(TimeoutError): Steps(path).once('qa/owner', lost_response)
    with pytest.raises(RuntimeError, match='not replayed'):
        Steps(path).once('qa/owner', lambda: calls.append('duplicate'))
    assert calls == ['submitted']


def test_profile_failure_or_empty_result_is_not_completion():
    for status, items in [('failed', []), ('complete', [])]:
        with pytest.raises(RuntimeError):
            wait_profile(lambda: {'jobs': [{'job_id': 'j', 'status': status}], 'items': items}, 'j', seconds=0)
