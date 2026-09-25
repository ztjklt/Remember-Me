"""Guided questions react to model coverage and calibration gaps."""

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
