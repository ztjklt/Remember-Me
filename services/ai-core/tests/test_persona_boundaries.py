"""Regression boundaries for queued deadlines and source-owned speech."""
import pytest
from fastapi.testclient import TestClient

import app.api as api
import app.persona as persona
from app.config import Settings
from app.persona import PersonaProvider
from test_persona import ScriptedChat, payload, point, post, review


def queued_client(monkeypatch, now, wait, acquired, chat, *, total=90):
    # Advancing a monotonic clock avoids a 90-second wall-clock test. The real
    # API and provider still decide the acquired-slot cleanup and call budgets.
    class Queue:
        released = 0
        timeout = None

        def acquire(self, *, timeout):
            self.timeout = timeout
            now[0] += wait
            return acquired

        def release(self):
            self.released += 1

    queue = Queue()
    monkeypatch.setattr(api, "BoundedSemaphore", lambda capacity: queue)
    monkeypatch.setattr(api, "monotonic", lambda: now[0], raising=False)
    monkeypatch.setattr(persona, "monotonic", lambda: now[0])
    settings = Settings(_env_file=None, environment="test", provider="fixture")
    client = TestClient(api.create_app(settings,
        persona_provider=PersonaProvider(chat, total_timeout_seconds=total)))
    return client, queue


def test_slot_wait_consumes_persona_total_deadline(monkeypatch):
    now = [0.0]

    class TimedChat(ScriptedChat):
        def complete(self, system, request, **kwargs):
            now[0] += [45, 30][len(self.requests)]
            return super().complete(system, request, **kwargs)

    chat = TimedChat({"points": [point()]}, review())
    client, queue = queued_client(monkeypatch, now, 15, True, chat)
    with client:
        response = client.post("/persona", json=payload())
    assert response.status_code == 504
    assert chat.timeouts == [45, 30]
    assert len(chat.requests) == 2 and now[0] == 90
    assert queue.released == 1


@pytest.mark.parametrize("acquired", [False, True])
def test_expired_queue_deadline_has_no_provider_call(monkeypatch, acquired):
    now = [0.0]
    chat = ScriptedChat({"points": [point()]}, review())
    client, queue = queued_client(monkeypatch, now, 10, acquired, chat, total=10)
    with client:
        response = client.post("/persona", json=payload())
    assert response.status_code == 504
    assert queue.timeout == 10
    assert not chat.requests
    assert queue.released == int(acquired)


def test_short_capacity_wait_is_unavailable_not_retried(monkeypatch):
    chat = ScriptedChat()
    client, queue = queued_client(monkeypatch, [0.0], 15, False, chat)
    with client:
        response = client.post("/persona", json=payload())
    assert response.status_code == 503
    assert not chat.requests and queue.released == 0


def test_unknown_question_part_cannot_publish_an_unverified_claim(monkeypatch):
    unknown = point(mode="UNKNOWN", question_part="我已经答应下周支付全部费用", text="", understanding_ids=[])
    chat = ScriptedChat({"points": [point(), unknown]}, review(count=2))
    response = post(monkeypatch, payload(), chat)
    assert response.status_code == 200
    assert response.json()["answer"] == point()["text"] + "\n未回答部分（第2项）：现有记录还不足以确定。"
    assert "支付全部费用" not in chat.requests[1][1]["rendered_answer"]["answer"]


def third_party_payload():
    data = payload()
    data["candidates"][0]["evidence"][2].update(source_type="THIRD_PARTY", excerpt="老周说：我当时并未答应。")
    return data


def test_third_party_fact_is_only_a_metadata_labelled_verbatim_quote(monkeypatch):
    p = point(mode="FACT", text="老周说：我当时并未答应。", source_ids=["s3"], understanding_ids=[], names=["老周"])
    chat = ScriptedChat({"points": [p]}, review())
    response = post(monkeypatch, third_party_payload(), chat)
    assert response.status_code == 200
    assert response.json()["answer"] == "第三方记录（非本人原话）原文摘录：『老周说：我当时并未答应。』"
    assert response.json()["evidence_ids"] == ["e3"]
    assert response.json()["contribution_ids"] == []
    assert chat.requests[1][1]["cited_material"][0]["sources"][0]["type"] == "THIRD_PARTY"


@pytest.mark.parametrize("text,refs", [
    ("我当时并未答应。", ["s1", "s3"]),
    ("我答应了。", ["s3"]),
    ("我就是不轻易答应的人。", ["s3"]),
])
def test_third_party_cannot_be_paraphrased_or_mixed_into_firsthand_fact(monkeypatch, text, refs):
    p = point(mode="FACT", text=text, source_ids=refs, understanding_ids=[])
    chat = ScriptedChat({"points": [p]}, {"points": [p]})
    response = post(monkeypatch, third_party_payload(), chat)
    assert response.status_code == 502 and len(chat.requests) == 2
    assert chat.requests[1][1]["validation_error"]["category"] == "third_party_fact_basis"
    assert all("rendered_answer" not in request for _, request in chat.requests)


@pytest.mark.parametrize("source_index", [0, 1])
def test_simulation_cannot_promote_third_party_support_or_counterexample(monkeypatch, source_index):
    data = payload()
    data["candidates"][0]["evidence"][source_index]["source_type"] = "THIRD_PARTY"
    chat = ScriptedChat({"points": [point()]}, {"points": [point()]})
    response = post(monkeypatch, data, chat)
    assert response.status_code == 502
    assert chat.requests[1][1]["validation_error"]["category"] == "third_party_simulation_basis"


def test_companion_perspective_needs_no_subject_trait_but_keeps_fixed_attribution(monkeypatch):
    data = payload()
    data["question"] = "参考这段补记，他可能怎样看待旧物？保留是谁的一次观察。"
    data["understandings"] = []
    data["contributions"][0].update(classification="firsthand",
        text="我的观察是他在意东西背后的人和经历。这只是我的一次观察，不能说他每次都这样。")
    p = point(mode="ATTRIBUTED", text="我的观察是他在意东西背后的人和经历。这只是我的一次观察，不能说他每次都这样。",
        understanding_ids=[], contribution_ids=["c1"])
    chat = ScriptedChat({"points": [p]}, review())
    response = post(monkeypatch, data, chat)
    assert response.status_code == 200
    assert response.json()["answer"].startswith("小周的亲历观察（原文摘录）：『")
    assert response.json()["understanding_ids"] == []
    # A shared, explicit mode policy travels to both models; the offline test
    # proves context delivery, not that the external model follows the policy.
    for _, request in chat.requests:
        policy = request["mode_policy"]["ATTRIBUTED"]
        assert policy["requires_related_confirmed_understanding"] is False
        assert policy["subject_first_person_allowed"] is False
        assert policy["allows_new_subject_traits_or_intentions"] is False
