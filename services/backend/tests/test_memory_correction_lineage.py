from sqlalchemy import select
from app.models import Episode, Evidence, MemoryItem
from app.materials import effective_materials
from test_agent_workbench import setup_pair
from test_language_support import reviewed_note


def prepared(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    row = session.get(Episode, ep)
    wrong = '我曾误怪桂芳动了钥匙。'
    row.transcript = wrong + '我以前在机械厂修机器。'
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    source = session.get(Evidence, memory.evidence_ids[0])
    source.excerpt, source.span_start, source.span_end = wrong, 0, len(wrong)
    source.source_ref = f'episode:{ep}#span:0-{len(wrong)}'
    memory.content = wrong
    session.commit()
    return owner, reader, oh, rh, ep, cloud, memory.memory_item_id, wrong


def text(session, owner, ep):
    session.expire_all()
    result = '\n'.join(e['excerpt'] for c in effective_materials(session, owner.subject_id, {ep}) for e in c['evidence'])
    session.commit()
    return result


def test_correction_keeps_unrelated_fact_and_never_revives_old_claim(app, client, session):
    owner, _, oh, _, ep, _, mid, wrong = prepared(app, client, session)
    path = f'/api/v1/subjects/{owner.subject_id}/memories/{mid}'
    for revised in ['曾指责桂芳动过钥匙，但不能确定她是否动过。', '曾指责桂芳；谁动过钥匙尚不清楚。']:
        assert client.patch(path, headers=oh, json={'content': revised}).status_code == 200
        current = text(session, owner, ep)
        assert revised in current
        assert '在机械厂修机器' in current
        assert wrong not in current
    assert wrong in session.get(Episode, ep).transcript  # Original remains history.
    assert client.delete(path, headers=oh).status_code == 200
    current = text(session, owner, ep)
    assert wrong not in current and '在机械厂修机器' in current
    assert revised not in current


def test_correction_does_not_edit_another_actor_or_resurrect_superseded(app, client, session):
    owner, _, oh, rh, ep, _, mid, wrong = prepared(app, client, session)
    path = f'/api/v1/subjects/{owner.subject_id}/memories/{mid}'
    assert client.patch(path, headers=rh, json={'content': '替本人修改'}).status_code == 404
    memory = session.get(MemoryItem, mid)
    memory.review_state = 'superseded';session.commit()
    assert client.patch(path, headers=oh, json={'content': '恢复旧说法'}).status_code == 409


def test_written_note_correction_and_deletion_keep_audio_facts(app, client, session):
    owner, _, oh, _, ep, _ = reviewed_note(app, client, session)
    note = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep, MemoryItem.model_version == 'owner-input'))
    path = f'/api/v1/subjects/{owner.subject_id}/memories/{note.memory_item_id}'
    for content in ['隗师傅是以前的同事。', '隗师傅是同事，不是亲戚。']:
        assert client.patch(path, headers=oh, json={'content':content}).status_code == 200
        assert '我喜欢散步。' in text(session, owner, ep)
    assert client.delete(path, headers=oh).status_code == 200
    assert '我喜欢散步。' in text(session, owner, ep)


def test_overlapping_summary_cannot_reappear_in_search_or_person_model(app, client, session):
    owner, _, oh, _, ep, _, mid, wrong = prepared(app, client, session)
    original = session.get(MemoryItem, mid)
    sibling = MemoryItem(memory_item_id='overlapping', episode_id=ep, ordinal=99,
        memory_type=original.memory_type, content='桂芳被误怪了', source_type=original.source_type,
        evidence_ids=list(original.evidence_ids), confidence=.8, model_version='test',
        prompt_version='test', schema_version='v1', item_metadata={'domain':'RELATIONSHIPS'})
    session.add(sibling);session.commit()
    from types import SimpleNamespace
    from app.api.calibration import _snapshot, _check_source
    frozen = SimpleNamespace(subject_id=owner.subject_id, source_snapshot=_snapshot(session,owner.subject_id,['overlapping']),
        locked_evidence_ids=list(sibling.evidence_ids), status='awaiting_human')
    assert client.patch(f'/api/v1/subjects/{owner.subject_id}/memories/{mid}', headers=oh,
        json={'content':'曾指责桂芳；谁动过钥匙尚不清楚。'}).status_code == 200
    response = client.get(f'/api/v1/subjects/{owner.subject_id}/memory-search',headers=oh,params={'q':'桂芳'})
    assert response.status_code == 200, response.text
    assert '桂芳被误怪了' not in response.text
    response = client.get(f'/api/v1/subjects/{owner.subject_id}/person-model',headers=oh)
    assert '桂芳被误怪了' not in response.text
    response = client.get(f'/api/v1/episodes/{ep}/result',headers=oh)
    assert '桂芳被误怪了' not in response.text
    session.expire_all()
    assert not _check_source(session, frozen)
    assert frozen.status == 'stale'
