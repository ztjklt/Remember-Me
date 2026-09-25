"""Person preview follows committed Memory and invalidates on feedback."""

from app.models import Actor
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token
from test_worker import advance, build_worker


def test_worker_materializes_and_feedback_rebuilds_person_preview(client, app, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    path = f"/api/v1/subjects/{seeded.subject_id}/person-model"
    empty = client.get(path, headers=auth)
    assert empty.status_code == 200
    assert empty.json()["revision"] == 0

    uploaded = client.post(
        "/api/v1/episodes", headers=auth,
        data={
            "subject_id": seeded.subject_id,
            "recording_consent_id": seeded.consent_id,
            "source": "IMPORT", "recorded_at": "2026-09-25T08:00:00Z",
            "audio_ref": "sample.m4a", "idempotency_key": "person-model-test",
        },
        files={"file": ("sample.m4a", b"audio", "audio/mp4")},
    )
    assert uploaded.status_code == 201
    advance(build_worker(app))
    profile = client.get(path, headers=auth)
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["revision"] == 1
    assert body["model_version"] == "person-preview-r1"
    assert len(body["domains"]["Episodic Memory"]) == 1
    item_id = body["source_memory_ids"][0]
    assert body["domains"]["Episodic Memory"][0]["memory_item_id"] == item_id
    assert body["domains"]["Episodic Memory"][0]["evidence_ids"]
    assert client.get(path, headers=auth).json()["revision"] == 1

    memory_path = f"/api/v1/subjects/{seeded.subject_id}/memories/{item_id}"
    assert client.put(
        memory_path + "/correction", headers=auth,
        json={"proposed_content": "That did not happen."},
    ).status_code == 200
    disputed = client.get(path, headers=auth).json()
    assert disputed["revision"] == 2
    assert disputed["source_memory_ids"] == []
    assert client.delete(memory_path + "/correction", headers=auth).status_code == 204
    assert client.get(path, headers=auth).json()["revision"] == 3
    assert client.delete(memory_path, headers=auth).status_code == 204
    removed = client.get(path, headers=auth).json()
    assert removed["revision"] == 4
    assert removed["domains"]["Episodic Memory"] == []

    other_token = generate_actor_token()
    session.add(Actor(actor_id="person_other", display_name="Other", token_hash=hash_actor_token(other_token)))
    session.commit()
    assert client.get(
        path, headers={"Authorization": f"Bearer {other_token}"},
    ).status_code == 404
