"""The locked-answer ordering and Actor isolation of calibration."""

from app.models import Actor
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from test_core_twin import _ready_episode


def test_calibration_locks_answer_before_human_submission(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    _ready_episode(client, session, seeded, auth)
    grant = client.post(
        "/api/v1/consents", headers=auth,
        json={"subject_id": seeded.subject_id, "scope": "CLOUD_TWIN"},
    )
    consent_id = grant.json()["consent_id"]
    path = f"/api/v1/subjects/{seeded.subject_id}/calibrations"
    initial = client.post(
        path, headers=auth,
        json={"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": consent_id},
    )
    assert initial.status_code == 201, initial.text
    before = initial.json()
    assert before["locked_answer"] == "我喜欢咖啡。"
    assert before["human_answer"] is None
    assert before["evidence_ids"] == ["ev_ios_1"]

    # A correction after the lock changes the live Twin route, not the
    # historical answer against which the human will calibrate.
    memory_path = f"/api/v1/subjects/{seeded.subject_id}/memories"
    memory_id = client.get(memory_path, headers=auth).json()["items"][0]["memory_item_id"]
    client.put(
        f"{memory_path}/{memory_id}/correction", headers=auth,
        json={"proposed_content": "我不喜欢咖啡。"},
    )
    assert client.post(
        f"/api/v1/subjects/{seeded.subject_id}/twin/query", headers=auth,
        json={"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": consent_id},
    ).json()["response_type"] == "SIMULATION"

    answer_path = f"{path}/{before['calibration_id']}/answer"
    answer = {
        "human_answer": "我现在不喜欢咖啡。",
        "gaps": {
            "decision": False, "reasoning": False, "value_priority": True,
            "emotional_reaction": False, "expression": True,
        },
    }
    completed = client.post(answer_path, headers=auth, json=answer)
    assert completed.status_code == 200, completed.text
    assert completed.json()["locked_answer"] == before["locked_answer"]
    assert completed.json()["human_answer"] == answer["human_answer"]
    assert completed.json()["gaps"] == answer["gaps"]
    assert client.post(answer_path, headers=auth, json=answer).status_code == 200
    assert client.post(
        answer_path, headers=auth,
        json={**answer, "human_answer": "another answer"},
    ).status_code == 409

    other_token = generate_actor_token()
    session.add(Actor(actor_id="cal_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    other_auth = {"Authorization": f"Bearer {other_token}"}
    assert client.get(path, headers=other_auth).json() == []
    assert client.post(answer_path, headers=other_auth, json=answer).status_code == 404

    assert client.post(f"/api/v1/consents/{consent_id}/revoke", headers=auth).status_code == 200
    assert client.post(
        path, headers=auth,
        json={"question": "我喜欢咖啡吗？", "cloud_twin_consent_id": consent_id},
    ).status_code == 403
    assert client.get(path, headers=auth).json()[0]["locked_answer"] == before["locked_answer"]
