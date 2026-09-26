from datetime import timedelta

from sqlalchemy import select
import json
from pathlib import Path
from jsonschema import Draft202012Validator

from app.models import CaptureQuestion, DeviceCredential, Episode, MemoryAudit, MemoryItem, PairingCode, PersonTrait, utcnow
from app.repositories.person_model import PersonModelRepository
from app.errors import SttUnavailable
from app.seed import seed_development_data
from app.tokens import hash_actor_token
from app.worker import ProcessingWorker


def test_second_episode_correction_delete_and_subject_isolation(app, client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    other = seed_development_data(session, subject_name="Other", actor_name="Other")
    headers = {"Authorization": "Bearer " + seeded.actor_token}
    worker = ProcessingWorker(app.state.database, app.state.object_store,
                              app.state.stt_provider, app.state.ai_client,
                              backoff_seconds=0)
    for index in range(2):
        response = client.post("/api/v1/episodes", headers=headers,
            data={"subject_id": seeded.subject_id, "recording_consent_id": seeded.consent_id,
                  "idempotency_key": f"capture-{index}", "source": "IOS_MIC",
                  "recorded_at": "2026-09-26T09:00:00Z", "audio_ref": f"voice-{index}.m4a"},
            files={"file": ("voice.m4a", b"FAKE-AUDIO" + bytes([index]), "audio/mp4")})
        assert response.status_code == 201, response.text
        for _ in range(3):
            worker.run_once()
    model = client.get(f"/api/v1/subjects/{seeded.subject_id}/person-model", headers=headers).json()
    assert model["version"] == 2
    assert len(model["domains"]) == 7
    schema_path = Path(__file__).resolve().parents[3] / "packages/contracts/schemas/integration-contract-v0.2.schema.json"
    Draft202012Validator(json.loads(schema_path.read_text())).validate(model)
    memories = client.get(f"/api/v1/subjects/{seeded.subject_id}/memories", headers=headers).json()["items"]
    assert len(memories) == 2
    archive = client.get(f"/api/v1/subjects/{seeded.subject_id}/episodes", headers=headers).json()["items"]
    assert len(archive) == 2
    assert all(item["transcript"] and item["status"] == "ready" for item in archive)
    first = memories[0]
    assert first["evidence"][0]["excerpt"]
    question = client.get(f"/api/v1/subjects/{seeded.subject_id}/questions", headers=headers).json()["items"]
    assert len(question) == 1
    Draft202012Validator(json.loads(schema_path.read_text())).validate(question[0])
    assert client.get(f"/api/v1/subjects/{other.subject_id}/person-model", headers=headers).status_code == 404
    assert client.get(f"/api/v1/subjects/{other.subject_id}/episodes", headers=headers).status_code == 404
    corrected = client.patch(f"/api/v1/subjects/{seeded.subject_id}/memories/{first['memory_item_id']}",
                             headers=headers, json={"content": "我改正这段经历的描述"})
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["model_version"] == 3
    session.expire_all()
    trait = session.scalar(select(PersonTrait).where(PersonTrait.statement == "我改正这段经历的描述"))
    assert trait and trait.source_type == "CALIBRATION"
    assert session.scalar(select(MemoryAudit).where(MemoryAudit.memory_item_id == first["memory_item_id"]))
    removed = client.delete(f"/api/v1/subjects/{seeded.subject_id}/memories/{first['memory_item_id']}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["model_version"] == 4
    assert len(client.get(f"/api/v1/subjects/{seeded.subject_id}/memories", headers=headers).json()["items"]) == 1
    assert client.get(f"/api/v1/episodes/{first['episode_id']}/result", headers=headers).json()["memory_items"] == []


def test_conflicting_memories_coexist_and_prompt_for_clarification(app, client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    headers = {"Authorization": "Bearer " + seeded.actor_token}
    worker = ProcessingWorker(app.state.database, app.state.object_store,
                              app.state.stt_provider, app.state.ai_client,
                              backoff_seconds=0)
    for index in range(2):
        response = client.post("/api/v1/episodes", headers=headers,
            data={"subject_id": seeded.subject_id, "recording_consent_id": seeded.consent_id,
                  "idempotency_key": f"conflict-{index}", "source": "IOS_MIC",
                  "recorded_at": "2026-09-26T09:00:00Z", "audio_ref": f"voice-{index}.m4a"},
            files={"file": ("voice.m4a", b"AUDIO" + bytes([index]), "audio/mp4")})
        assert response.status_code == 201
        for _ in range(3):
            worker.run_once()
    rows = list(session.scalars(select(MemoryItem).order_by(MemoryItem.created_at)))
    rows[0].memory_type = rows[1].memory_type = "PREFERENCE"
    rows[0].content = "我喜欢咖啡"
    rows[1].content = "我不喜欢咖啡"
    rows[0].item_metadata = rows[1].item_metadata = {"domain": "PREFERENCES"}
    session.flush()
    PersonModelRepository(session).rebuild(seeded.subject_id)
    session.commit()
    traits = list(session.scalars(select(PersonTrait).where(PersonTrait.subject_id == seeded.subject_id)))
    assert len(traits) == 2
    assert {item.status for item in traits} == {"unresolved"}
    assert all(item.counter_evidence_ids for item in traits)
    question = session.scalar(select(CaptureQuestion).where(
        CaptureQuestion.subject_id == seeded.subject_id,
        CaptureQuestion.status == "pending"))
    assert question and question.reason == "contradiction"
    response = client.delete(f"/api/v1/subjects/{seeded.subject_id}/memories/{rows[1].memory_item_id}", headers=headers)
    assert response.status_code == 200
    session.expire_all()
    survivor = session.scalar(select(PersonTrait).where(PersonTrait.subject_id == seeded.subject_id))
    assert survivor.status == "active"
    assert survivor.counter_evidence_ids == []


def test_pairing_claim_once_over_https_and_new_device_token(app, client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    code = "A-long-one-time-pairing-code-12345"
    session.add(PairingCode(code_hash=hash_actor_token(code), actor_id=seeded.actor_id,
                            subject_id=seeded.subject_id, expires_at=utcnow() + timedelta(minutes=5)))
    session.commit()
    path = "/api/v1/local-pairing/claim"
    assert client.post(path, json={"code": code}).status_code == 422
    secure = client.post(path, json={"code": code}, headers={"X-Forwarded-Proto": "https"})
    # TestClient's ASGI scheme is http; a forwarded header must not bypass TLS.
    assert secure.status_code == 422
    client.base_url = "https://testserver"
    claimed = client.post(path, json={"code": code})
    assert claimed.status_code == 200, claimed.text
    assert client.post(path, json={"code": code}).status_code == 422
    token = claimed.json()["actor_token"]
    assert session.get(DeviceCredential, hash_actor_token(token))
    assert client.get("/api/v1/session", headers={"Authorization": "Bearer " + token}).status_code == 200


def test_failed_processing_can_resume_without_creating_another_episode(app, client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    headers = {"Authorization": "Bearer " + seeded.actor_token}
    fields = {"subject_id": seeded.subject_id, "recording_consent_id": seeded.consent_id,
              "idempotency_key": "phone-draft-id-1", "source": "IOS_MIC",
              "recorded_at": "2026-09-26T09:00:00Z", "audio_ref": "phone-draft.m4a"}
    def upload():
        return client.post("/api/v1/episodes", headers=headers, data=fields,
                           files={"file": ("voice.m4a", b"UNIQUE-PHONE-AUDIO", "audio/mp4")})
    first = upload()
    assert first.status_code == 201
    repeated = upload()
    assert repeated.status_code == 200
    episode_id = first.json()["episode_id"]
    assert repeated.json()["episode_id"] == episode_id
    class OfflineStt:
        def transcribe(self, audio, content_type):
            raise SttUnavailable("local Whisper is down")
    failed = ProcessingWorker(app.state.database, app.state.object_store,
                              OfflineStt(), app.state.ai_client,
                              max_attempts=1, backoff_seconds=0)
    failed.run_once()
    assert client.get(f"/api/v1/episodes/{episode_id}", headers=headers).json()["status"] == "failed"
    queued = client.post(f"/api/v1/episodes/{episode_id}/retry", headers=headers)
    assert queued.status_code == 200
    recovered = ProcessingWorker(app.state.database, app.state.object_store,
                                 app.state.stt_provider, app.state.ai_client,
                                 backoff_seconds=0)
    for _ in range(3):
        recovered.run_once()
    assert client.get(f"/api/v1/episodes/{episode_id}", headers=headers).json()["status"] == "ready"
    assert session.query(Episode).count() == 1
    assert client.get(f"/api/v1/episodes/{episode_id}/audio", headers=headers).content == b"UNIQUE-PHONE-AUDIO"
