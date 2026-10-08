"""Regression checks for durable conclusions and a usable next-capture loop."""
from sqlalchemy import select

from app.models import CaptureQuestion, Episode, GraphFact, MemoryItem, PersonTrait
from app.repositories.person_model import PersonModelRepository
from app.seed import seed_development_data
from app.worker import ProcessingWorker


def capture(client, app, seeded, headers, key, text):
    response = client.post('/api/v1/episodes', headers=headers,
        data={'subject_id': seeded.subject_id, 'recording_consent_id': seeded.consent_id,
              'idempotency_key': key, 'source': 'IOS_MIC',
              'recorded_at': '2026-10-08T09:00:00Z', 'audio_ref': key + '.m4a'},
        files={'file': (key + '.m4a', b'SYNTHETIC-TEST-' + key.encode(), 'audio/mp4')})
    assert response.status_code == 201, response.text
    episode_id = response.json()['episode_id']
    worker = ProcessingWorker(app.state.database, app.state.object_store,
                              app.state.stt_provider, app.state.ai_client, backoff_seconds=0)
    worker.run_once()
    assert client.patch(f'/api/v1/episodes/{episode_id}/transcript-review', headers=headers,
                        json={'transcript': text}).status_code == 200
    worker.run_once()
    worker.run_once()
    assert client.get(f'/api/v1/episodes/{episode_id}', headers=headers).json()['status'] == 'ready'
    return episode_id


def test_correction_keeps_legacy_identity_and_unrelated_conclusions(app, client, session):
    own = seed_development_data(session, subject_name='Own', actor_name='Own')
    headers = {'Authorization': 'Bearer ' + own.actor_token}
    first = capture(client, app, own, headers, 'one', '我叫小林。')
    session.expire_all()
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == first))
    original_evidence = list(memory.evidence_ids)
    trait = session.scalar(select(PersonTrait).where(PersonTrait.subject_id == own.subject_id))
    fact = session.scalar(select(GraphFact).where(GraphFact.subject_id == own.subject_id))
    # Older deployments accepted proposal IDs. Upgrading must preserve those IDs.
    trait.trait_id = 'legacy-trait-id'
    fact.fact_id = 'legacy-fact-id'
    session.commit()
    capture(client, app, own, headers, 'two', '我在杭州读书。')
    session.expire_all()
    traits_before = {row.trait_id: row.statement for row in session.scalars(
        select(PersonTrait).where(PersonTrait.subject_id == own.subject_id))}
    assert 'legacy-trait-id' in traits_before
    other_id = next(key for key in traits_before if key != 'legacy-trait-id')
    correction = client.patch(f'/api/v1/subjects/{own.subject_id}/memories/{memory.memory_item_id}',
                              headers=headers, json={'content': '我叫小琳，不是小林。'})
    assert correction.status_code == 200
    session.expire_all()
    current = session.get(PersonTrait, 'legacy-trait-id')
    assert current.statement == '我叫小琳，不是小林。'
    assert current.source_type == 'CALIBRATION'
    assert current.evidence_ids != original_evidence
    assert session.get(PersonTrait, other_id).statement == traits_before[other_id]
    assert session.get(GraphFact, 'legacy-fact-id').content == current.statement
    deleted = client.delete(f'/api/v1/subjects/{own.subject_id}/memories/{memory.memory_item_id}', headers=headers)
    assert deleted.status_code == 200
    session.expire_all()
    assert session.get(PersonTrait, 'legacy-trait-id') is None
    assert session.get(GraphFact, 'legacy-fact-id') is None
    assert session.get(PersonTrait, other_id).statement == traits_before[other_id]


def test_pending_question_is_reused_until_answered(app, client, session):
    own = seed_development_data(session, subject_name='Own', actor_name='Own')
    headers = {'Authorization': 'Bearer ' + own.actor_token}
    capture(client, app, own, headers, 'first', '昨天我去公园散步。')
    path = f'/api/v1/subjects/{own.subject_id}/questions'
    original = client.get(path, headers=headers).json()['items'][0]
    capture(client, app, own, headers, 'second', '今天我去了图书馆。')
    current = client.get(path, headers=headers).json()['items'][0]
    assert current['question_id'] == original['question_id']
    assert session.query(CaptureQuestion).filter_by(subject_id=own.subject_id).count() == 3
    PersonModelRepository(session).rebuild(own.subject_id, answered_question_id=current['question_id'])
    session.commit()
    next_question = client.get(path, headers=headers).json()['items'][0]
    assert next_question['target_domain'] != current['target_domain']
    assert session.get(CaptureQuestion, current['question_id']).status == 'answered'


def test_provider_ids_cannot_collide_between_memories(app, client, session):
    own = seed_development_data(session, subject_name='Own', actor_name='Own')
    headers = {'Authorization': 'Bearer ' + own.actor_token}
    for index in range(2):
        episode_id = capture(client, app, own, headers, f'collision-{index}', f'第{index}次去公园。')
        session.expire_all()
        memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == episode_id))
        episode = session.get(Episode, episode_id)
        episode.model_proposals = {
            'persona_updates': [{'trait_id': 'same-model-id', 'statement': memory.content,
                                 'domain': 'EPISODIC_MEMORY', 'evidence_ids': memory.evidence_ids}],
            'graph_updates': [{'fact_id': 'same-model-id', 'content': memory.content,
                               'kind': 'EVENT', 'evidence_ids': memory.evidence_ids}],
        }
        session.commit()
    PersonModelRepository(session).rebuild(own.subject_id)
    session.commit()
    traits = list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id == own.subject_id)))
    facts = list(session.scalars(select(GraphFact).where(GraphFact.subject_id == own.subject_id)))
    assert len({row.trait_id for row in traits}) == len(traits) == 2
    assert len({row.fact_id for row in facts}) == len(facts) == 2
    assert all(row.trait_id != 'same-model-id' for row in traits)
