"""Oversized persona context must fail locally, before any model request."""
from copy import deepcopy
import json

import httpx
import pytest
from sqlalchemy import select

from app.models import TwinAnswer
from app.twin_client import TwinClient
from test_persona_dialogue import cloud, enable
from test_reader_understandings import candidate, confirm, prepare


def request_context(app, client, session):
    owner, _, headers, _, _, _, source, _, root = prepare(app, client, session)
    row = candidate(session, owner, [source])
    confirm(client, root, headers, row)
    enable(client, root, headers, source)
    body = {"question": "遇到新开支会怎么考虑？", "mode": "persona",
            "cloud_consent_id": cloud(client, owner.subject_id, headers)}
    app.state.settings.ai_backend = "http"
    app.state.twin_client = TwinClient("http://ai.invalid", 1)
    return headers, f"/api/v1/subjects/{owner.subject_id}/twin/answers", body


def inflate(kind, payload):
    if kind == "example_count":
        payload["examples"] = [{"id": f"style-{i}", "text": "说话例子"} for i in range(9)]
    elif kind == "example_text":
        payload["examples"] = [{"id": f"style-{i}", "text": "甲" * 1400} for i in range(3)]
    elif kind == "understanding_count":
        trait = payload["understandings"][0]
        payload["understandings"] = [dict(trait, id=f"trait-{i}") for i in range(33)]
    elif kind == "understanding_text":
        trait = payload["understandings"][0]
        payload["understandings"] = [dict(trait, id=f"trait-{i}", statement="甲" * 1000,
                                            context="乙" * 1000) for i in range(7)]
    return payload


@pytest.mark.parametrize("kind", ["example_count", "example_text", "understanding_count", "understanding_text"])
def test_over_budget_persona_never_calls_worker_or_saves_answer(app, client, session, monkeypatch, kind):
    headers, path, body = request_context(app, client, session)
    # Shape the existing authorized projection; permissions and source checks
    # still run through the real endpoint. The private worker rejects these sizes.
    if kind.startswith("example"):
        import app.narrative as narrative
        visible = narrative.visible_records
        def records(*args, **kwargs):
            rows = visible(*args, **kwargs)
            style = next(row for row in rows if row["kind"] == "style")
            changed = inflate(kind, {"examples": []})["examples"]
            return [dict(style, id=item["id"], text=item["text"]) for item in changed]
        monkeypatch.setattr(narrative, "visible_records", records)
    else:
        import app.person_context as person
        visible = person.persona_understandings
        monkeypatch.setattr(person, "persona_understandings", lambda *a, **kw:
                            inflate(kind, {"understandings": visible(*a, **kw)})["understandings"])
    calls = []
    def worker(url, **kwargs):
        calls.append(deepcopy(kwargs["json"]))
        return httpx.Response(422, json={"detail": "Private persona input budget exceeded"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", worker)
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 413, response.text
    assert response.json()["error_code"] == "CONTEXT_TOO_LARGE"
    assert calls == []
    assert list(session.scalars(select(TwinAnswer))) == []


@pytest.mark.parametrize('kind,count', [('examples', 8), ('understandings', 32)])
def test_private_count_boundary_preserves_complete_context(kind, count):
    from app.persona_context import require_persona_budget
    data = {'question': '问题', 'candidates': [], 'examples': [], 'understandings': [], 'contributions': []}
    example = {'id': 'style', 'text': '原话'}
    trait = {'id': 'trait', 'statement': '条件化理解', 'context': '本人所述情境',
             'evidence_ids': [], 'counter_evidence_ids': []}
    data[kind] = [dict(example if kind == 'examples' else trait, id=str(i)) for i in range(count)]
    original = deepcopy(data)
    require_persona_budget(data)
    assert data == original


@pytest.mark.parametrize('kind,count,text', [('examples', 4, '甲' * 1000),
                                            ('understandings', 12, '乙' * 1000)])
def test_private_text_boundary_is_not_truncated(kind, count, text):
    from app.persona_context import require_persona_budget
    data = {'question': '问题', 'candidates': [], 'examples': [], 'understandings': [], 'contributions': []}
    example = {'id': 'style', 'text': text}
    trait = {'id': 'trait', 'statement': text, 'context': '', 'evidence_ids': [], 'counter_evidence_ids': []}
    data[kind] = [dict(example if kind == 'examples' else trait, id=str(i)) for i in range(count)]
    original = deepcopy(data)
    require_persona_budget(data)
    assert data == original


@pytest.mark.parametrize('kind', ['candidate_count', 'evidence_count', 'evidence_occurrences', 'request_size'])
def test_remaining_private_source_budgets_fail_before_transport(kind):
    from app.materials import ContextTooLarge
    from app.persona_context import require_persona_budget
    data = {'question': '问题', 'candidates': [], 'examples': [], 'understandings': [], 'contributions': []}
    evidence = {'evidence_id': 'e1', 'excerpt': '原文'}
    if kind == 'candidate_count':
        data['candidates'] = [{'evidence': [evidence]} for _ in range(257)]
    elif kind == 'evidence_count':
        data['candidates'] = [{'evidence': [dict(evidence, evidence_id=str(i)) for i in range(257)]}]
    elif kind == 'evidence_occurrences':
        data['candidates'] = [{'evidence': [evidence] * 1025}]
    else:
        data['candidates'] = [{'evidence': [evidence], 'statement': '甲' * 120000}]
    original = deepcopy(data)
    with pytest.raises(ContextTooLarge):
        require_persona_budget(data)
    assert data == original


@pytest.mark.parametrize('mode', ['persona', 'evidence'])
def test_nine_reviewed_examples_are_recoverable_through_evidence_mode(app, client, session, mode):
    owner, _, headers, _, _, _, source, _, root = prepare(app, client, session)
    row = candidate(session, owner, [source])
    confirm(client, root, headers, row)
    enable(client, root, headers, source)
    # All nine records are valid, confirmed original excerpts, created through
    # the public API. Archive growth alone must not become a worker outage.
    for i in range(8):
        created = client.post(root + '/narrative/records', headers=headers, json={
            'kind': 'style', 'title': f'原话范例{i}', 'text': source['excerpt'],
            'facets': ['EXPRESSION'], 'evidence_ids': [source['evidence_id']]})
        assert created.status_code == 201, created.text
        record = created.json()
        confirmed = client.post(root + '/narrative/records/' + record['id'] + '/confirm',
                                headers=headers, json={'revision': record['revision']})
        assert confirmed.status_code == 200, confirmed.text

    class Worker:
        calls = 0

        def answer(self, question, candidates):
            self.calls += 1
            return dict(answer='记录中提到平时会省着花。', response_type='SIMULATION',
                        evidence_ids=[source['evidence_id']], confidence=.6, model_version='fixture')

        def persona(self, payload):
            pytest.fail('An oversized persona request reached the model')

        def express(self, answer, examples):
            pytest.fail('An oversized optional expression request reached the model')

    worker = Worker()
    app.state.twin_client = worker
    app.state.settings.ai_backend = 'http'
    response = client.post(f'/api/v1/subjects/{owner.subject_id}/twin/answers', headers=headers,
        json={'question': '遇到新开支会怎么考虑？', 'mode': mode,
              'cloud_consent_id': cloud(client, owner.subject_id, headers)})
    if mode == 'persona':
        assert response.status_code == 413, response.text
        assert response.json()['error_code'] == 'CONTEXT_TOO_LARGE'
        assert worker.calls == 0
        assert list(session.scalars(select(TwinAnswer))) == []
    else:
        assert response.status_code == 200, response.text
        assert worker.calls == 1
        assert response.json()['expression']['status'] == 'unavailable'
        assert len(list(session.scalars(select(TwinAnswer)))) == 1


def test_complete_budget_includes_default_fields_for_written_corrections():
    from app.materials import ContextTooLarge
    from app.persona_context import require_persona_budget
    source = dict(evidence_id='written', excerpt='甲' * 500, source_type='CALIBRATION',
                  episode_id='episode', recorded_at='2026-10-13T00:00:00+00:00', temporal_context='')
    data = dict(question='问题', examples=[], understandings=[], contributions=[], candidates=[
        dict(memory_item_id=f'm{i}', statement='摘要', domain=None, unresolved=False,
             traits=[], graph_facts=[], evidence=[source] * 32) for i in range(5)])
    wire_size = len(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    # Stay just inside the wire limit with individually valid statements. The
    # worker expands omitted span fields, pushing its complete model over it.
    remaining = 119999 - wire_size
    for row in data['candidates']:
        count = min(remaining, 24000 - len(row['statement']))
        row['statement'] += '乙' * count
        remaining -= count
    assert remaining == 0
    assert len(json.dumps(data, ensure_ascii=False, separators=(',', ':'))) == 119999
    original = deepcopy(data)
    with pytest.raises(ContextTooLarge):
        require_persona_budget(data)
    assert data == original
