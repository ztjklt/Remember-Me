"""Bounded, whole-source profile jobs; model doubles are not quality evidence."""
import pytest
from sqlalchemy import select

from app.profile_batches import plan_profile_batches
from app.models import Episode, ProfileCandidate, ProfileRefresh
from app.profiles import run_profile_once
from test_agent_workbench import setup_pair
from test_profile_material_version import Proposal


def material(eid, episode, text):
    return {'evidence_id': eid, 'episode_id': episode, 'excerpt': text}


def test_batching_preserves_complete_episode_and_qualifier():
    sources = [material('a', 'one', '我喜欢修东西。'),
               material('b', 'two', '我以前不同意。'),
               material('c', 'two', '后来觉得不一定对。')]
    batches = plan_profile_batches(sources, max_chars=17)
    assert batches == [sources[:1], sources[1:]]
    assert ''.join(s['excerpt'] for s in batches[-1]).endswith('不一定对。')


def test_batching_deduplicates_identity_but_not_different_sources():
    a = material('a', 'one', '同一原话')
    b = material('b', 'two', '同一原话')
    assert plan_profile_batches([a, a.copy(), b]) == [[a, b]]
    with pytest.raises(ValueError, match='重复证据'):
        plan_profile_batches([a, material('a', 'one', '不同')])


def test_preflight_rejects_oversize_episode_and_excess_batches():
    with pytest.raises(ValueError, match='完整录音'):
        plan_profile_batches([material('a', 'one', '123456')], max_chars=5)
    with pytest.raises(ValueError, match='批次'):
        plan_profile_batches([material(str(i), str(i), '123') for i in range(3)], max_chars=3, max_batches=2)
    assert plan_profile_batches([]) == []


def queue_two_large_episodes(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    existing = session.get(Episode, ep)
    existing.transcript += '。' + '甲' * 12500 + '。这不是永久偏好。'
    values = {c.name: getattr(existing, c.name) for c in Episode.__table__.columns}
    values.update(episode_id='ep_batch_second', idempotency_key='batch-second',
                  transcript='乙' * 12500 + '。后来我的想法变了。')
    session.add(Episode(**values)); session.commit()
    root = f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates'
    response = client.post(root+'/refresh', headers=oh, json={'cloud_consent_id': cloud})
    assert response.status_code == 202, response.text
    return response.json()['job_id'], owner, cloud, ep, oh


def test_worker_processes_all_batches_and_publishes_once(app, client, session):
    job, owner, _, _, oh = queue_two_large_episodes(app, client, session)
    class Recorder(Proposal):
        inputs = []
        def propose(self, materials):
            self.inputs.append(materials)
            return super().propose(materials)
    model = Recorder()
    run_profile_once(app.state.database, model)
    session.expire_all()
    assert session.get(ProfileRefresh, job).status == 'complete'
    assert len(model.inputs) == 2
    assert all(sum(len(m['excerpt']) for m in b) <= 24000 for b in model.inputs)
    assert all(len({m['episode_id'] for m in b}) == 1 for b in model.inputs)
    assert len(list(session.scalars(select(ProfileCandidate)))) == 2
    # Real confirmation must also support the large archive, not only creation.
    for row in session.scalars(select(ProfileCandidate)):
        response=client.post(f'/api/v1/workbench/subjects/{owner.subject_id}/profile-candidates/{row.candidate_id}/confirm',
                             headers=oh)
        assert response.status_code==200, response.text


@pytest.mark.parametrize('failure', ['invalid_second', 'source_changed', 'consent_revoked'])
def test_worker_never_publishes_partial_or_stale_batches(app, client, session, failure):
    job, owner, cloud, ep, _ = queue_two_large_episodes(app, client, session)
    class Changes(Proposal):
        def propose(self, materials):
            result = super().propose(materials)
            if self.calls == 1 and failure != 'invalid_second':
                with app.state.database.session() as writer:
                    if failure == 'source_changed':
                        writer.get(Episode, ep).transcript += '。补充。'
                    else:
                        from app.models import Consent
                        writer.get(Consent, cloud).status = 'revoked'
                    writer.commit()
            if self.calls == 2 and failure == 'invalid_second':
                result['candidates'][0]['evidence_ids'] = ['invented']
            return result
    model = Changes()
    run_profile_once(app.state.database, model)
    session.expire_all()
    assert session.get(ProfileRefresh, job).status == 'failed'
    assert not list(session.scalars(select(ProfileCandidate)))
    assert model.calls == (2 if failure == 'invalid_second' else 1)
