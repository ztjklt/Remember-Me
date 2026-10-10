"""Context must come exclusively from material already visible to this actor."""
import json
from sqlalchemy import select
from app.models import Episode, MemoryItem
from test_agent_workbench import setup_pair


def capture(app):
    seen = []
    class Inspect:
        def answer(self, question, candidates):
            seen.extend(candidates)
            return dict(answer='现有记录还不足以确定。', response_type='UNKNOWN',
                        evidence_ids=[], confidence=0, model_version='test')
    app.state.twin_client = Inspect()
    return seen


def test_unextracted_context_does_not_cut_negation_from_sentence(app, client, session):
    from app.models import Evidence
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    source=session.get(Evidence,memory.evidence_ids[0])
    text='我没有说搬家能解决所有困难。'
    session.get(Episode,ep).transcript=text
    source.excerpt='我没有说';source.span_start=0;source.span_end=4
    session.commit()
    seen=capture(app)
    assert client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers',headers=oh,
        json={'question':'搬家解决了所有困难吗？','cloud_consent_id':cloud}).status_code==200
    excerpts=[e['excerpt'] for c in seen for e in c['evidence']]
    assert text in excerpts
    assert '搬家能解决所有困难。' not in excerpts


def test_complete_context_never_expands_into_a_deleted_span(app, client, session):
    from app.models import Evidence
    from app.materials import effective_materials
    owner, reader, oh, rh, ep, cloud=setup_pair(app,client,session)
    memory=session.scalar(select(MemoryItem).where(MemoryItem.episode_id==ep))
    source=session.get(Evidence,memory.evidence_ids[0])
    text='我没有说搬家能解决所有困难。今天散步。'
    session.get(Episode,ep).transcript=text
    source.excerpt='我没有说';source.span_start=0;source.span_end=4
    memory.review_state='superseded';session.commit()
    excerpts=[e['excerpt'] for c in effective_materials(session,owner.subject_id,{ep}) for e in c['evidence']]
    assert not any('搬家' in e or '我没有说' in e for e in excerpts)
    assert '今天散步。' in excerpts


def test_twin_preserves_recording_and_text_positions(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    row = session.get(Episode, ep)
    row.transcript += '。邻居老周告诉我，他父亲以前开火车。'
    session.commit()
    seen = capture(app)
    response = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question':'谁的父亲开火车？', 'cloud_consent_id':cloud})
    assert response.status_code == 200, response.text
    sources = [e for c in seen for e in c['evidence']]
    assert sources and all(e['episode_id'] == ep for e in sources)
    assert all(e['recorded_at'] == '2026-09-26T09:00:00+00:00' for e in sources)
    assert all(row.transcript[e['span_start']:e['span_end']] == e['excerpt'] for e in sources)
    assert all(e['temporal_context'] == '' for e in sources)


def test_twin_context_never_reintroduces_deleted_or_private_text(app, client, session):
    owner, reader, oh, rh, ep, cloud = setup_pair(app, client, session)
    memory = session.scalar(select(MemoryItem).where(MemoryItem.episode_id == ep))
    text = session.get(Episode, ep).transcript
    session.get(Episode, ep).transcript += '。这段可以保留。'
    original = session.get(Episode, ep)
    values = {c.name:getattr(original,c.name) for c in Episode.__table__.columns}
    values.update(episode_id='private', idempotency_key='private', transcript='私密地点在山谷')
    session.add(Episode(**values));session.commit()
    assert client.delete(f'/api/v1/subjects/{owner.subject_id}/memories/{memory.memory_item_id}', headers=oh).status_code == 200
    seen = capture(app)
    assert client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question':'留下了什么？','cloud_consent_id':cloud}).status_code == 200
    assert text not in json.dumps(seen, ensure_ascii=False)
    # A second owner-private recording must not become neighboring context for a reader.
    root = f'/api/v1/workbench/subjects/{owner.subject_id}'
    # Use a new unmodified recording because corrected/deleted stories cannot be shared.
    values.update(episode_id='shared', idempotency_key='shared', transcript='我今天散步。')
    session.add(Episode(**values));session.commit()
    grant = client.post(root+'/grants', headers=oh, json={'episode_id':'shared',
        'reader_actor_id':reader.actor_id,'include_audio_confirmed':True,'cloud_processing_allowed':True})
    assert grant.status_code == 201, grant.text
    seen.clear()
    assert client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=rh,
        json={'question':'留下了什么？','cloud_consent_id':grant.json()['grant_id']}).status_code == 200
    assert all(e['episode_id'] == 'shared' for c in seen for e in c['evidence'])
    assert '私密地点' not in json.dumps(seen, ensure_ascii=False)


def test_written_supplement_has_no_invented_audio_position(app, client, session):
    from test_language_support import reviewed_note
    owner, reader, oh, rh, ep, cloud = reviewed_note(app, client, session)
    seen = capture(app)
    response = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=oh,
        json={'question':'隗师傅是谁？', 'cloud_consent_id':cloud})
    assert response.status_code == 200
    notes = [e for c in seen for e in c['evidence'] if e['source_type']=='CALIBRATION']
    assert notes and all(e['episode_id']==ep for e in notes)
    assert all('span_start' not in e and 'span_end' not in e for e in notes)
