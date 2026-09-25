"""Guided questions react to model coverage and calibration gaps."""

import httpx

from app.models import Actor, CalibrationSession, utcnow
from app.person_model import rebuild_person_model
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from test_core_twin import _ready_episode


def test_capture_plan_reorders_after_model_and_calibration(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    path = f"/api/v1/subjects/{seeded.subject_id}/capture-plan"
    empty = client.get(path, headers=auth)
    assert empty.status_code == 200
    assert empty.json()["model_version"] == "person-preview-r0"
    assert len(empty.json()["questions"]) == 4
    assert all(item["existing_facts"] == 0 for item in empty.json()["questions"])

    _ready_episode(client, session, seeded, auth)
    rebuild_person_model(session, subject_id=seeded.subject_id, actor_id=seeded.actor_id)
    session.commit()
    with_memory = client.get(path, headers=auth).json()
    assert with_memory["model_version"] == "person-preview-r1"
    assert with_memory["planning_method"] == "heuristic-v2"
    assert all(
        item["score"] == round(
            item["information_gain"] * item["importance"]
            * item["uncertainty"] * item["time_urgency"]
            / item["interaction_cost"], 3
        ) for item in with_memory["questions"]
    )

    consent_id = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"},
    ).json()["consent_id"]
    base = f"/api/v1/subjects/{seeded.subject_id}/calibrations"
    calibration_id = client.post(
        base, headers=auth,
        json={"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": consent_id},
    ).json()["calibration_id"]
    answer = client.post(
        f"{base}/{calibration_id}/answer", headers=auth,
        json={
            "human_answer": "我更在意家庭。",
            "gaps": {
                "decision": False, "reasoning": False, "value_priority": True,
                "emotional_reaction": False, "expression": False,
            },
        },
    )
    assert answer.status_code == 200
    calibration = session.get(CalibrationSession, calibration_id)
    calibration.confirmed_at = utcnow()
    session.commit()
    updated = client.get(path, headers=auth).json()
    assert updated["questions"][0]["domain"] == "Values & Beliefs"
    assert updated["questions"][0]["time_urgency"] == 1.5
    assert updated["planning_method"] == "heuristic-v3-contextual"
    assert "我更在意家庭" in updated["questions"][0]["question"]
    assert client.get(path + "?limit=5", headers=auth).status_code == 422

    calibration.dimension_gaps = {key: False for key in calibration.dimension_gaps}
    calibration.ai_assessment = {"expression": {"verdict": "DIFFERENT"}}
    session.commit()
    ai_guided = client.get(path, headers=auth).json()
    assert ai_guided["questions"][0]["domain"] == "Expression"
    assert ai_guided["questions"][0]["time_urgency"] == 1.5
    assert next(
        item for item in ai_guided["questions"] if item["domain"] == "Values & Beliefs"
    )["time_urgency"] == 1.0

    other_token = generate_actor_token()
    session.add(Actor(actor_id="capture_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    assert client.get(
        path, headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 404


def test_real_capture_plan_uses_model_generated_questions_and_followups(client, session, monkeypatch):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    client.app.state.settings.ai_backend = "http"

    def generated(url, *, json, **_kwargs):
        assert url.endswith("/capture/plan")
        assert json["coverage"]["Preferences"] == 0
        return httpx.Response(200, json={
            "questions": [{
                "domain": domain, "question": question,
                "followups": [followup], "rationale": "填补当前证据缺口",
                "information_gain": 1.5, "importance": 1.2, "uncertainty": 1.4,
                "time_urgency": 1.0, "interaction_cost": 1.0,
            } for domain, question, followup in [
                ("Identity", "哪段经历最能代表现在的你？", "那件事发生在什么时候？"),
                ("Preferences", "最近你开始喜欢什么新事物？", "是哪些经历让你喜欢它？"),
            ]],
            "model_version": "real-planner-model", "planning_version": "capture-planner-llm-v1",
        })

    monkeypatch.setattr("app.api.capture_plan.httpx.post", generated)
    response = client.get(f"/api/v1/subjects/{seeded.subject_id}/capture-plan", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["planning_method"] == "capture-planner-llm-v1"
    assert body["questions"][0]["followups"]
    assert body["questions"][0]["score"] > 0


def test_real_capture_plan_rebuilds_missing_persona_before_planning(client, session, monkeypatch):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, auth)
    client.app.state.settings.ai_backend = "http"

    def persona(url, *, json, **_kwargs):
        assert url.endswith("/persona/reconcile")
        memory_id = json["memories"][0]["memory_item_id"]
        return httpx.Response(200, json={
            "traits": [{"domain": "Preferences", "statement": "我喜欢咖啡。",
                        "support_memory_ids": [memory_id], "counter_memory_ids": [],
                        "context": None, "confidence": 0.9, "status": "current",
                        "conflict_type": None}],
            "entities": [], "relations": [],
            "model_version": "real-persona-v1", "schema_version": "persona-temporal-v1",
        })

    def planner(url, *, json, **_kwargs):
        assert url.endswith("/capture/plan")
        assert json["coverage"]["Preferences"] == 1
        assert json["traits"][0]["statement"] == "我喜欢咖啡。"
        return httpx.Response(200, json={
            "questions": [{
                "domain": domain, "question": question,
                "followups": ["那是在什么时候发生的？"], "rationale": "补充具体经历",
                "information_gain": 1.0, "importance": 1.0,
                "uncertainty": 1.0, "time_urgency": 1.0,
                "interaction_cost": 1.0,
            } for domain, question in [
                ("Identity", "哪件事最能说明你是谁？"),
                ("Relationships", "谁在这件事里影响了你？"),
            ]],
            "model_version": "real-planner-v1", "planning_version": "capture-planner-llm-v1",
        })

    def provider(url, **kwargs):
        if url.endswith("/persona/reconcile"):
            return persona(url, **kwargs)
        return planner(url, **kwargs)

    monkeypatch.setattr("app.person_model.httpx.post", provider)
    response = client.get(f"/api/v1/subjects/{seeded.subject_id}/capture-plan", headers=auth)
    assert response.status_code == 200, response.text
