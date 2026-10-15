import json
from pathlib import Path
from jsonschema import Draft202012Validator
from sqlalchemy import select
from app.seed import seed_development_data
from app.models import Episode, Job, MemoryItem, Evidence
from app.worker import ProcessingWorker

def capture(client, own, key):
    h = {"Authorization": "Bearer " + own.actor_token}
    r = client.post("/api/v1/episodes", headers=h, data={
        "subject_id": own.subject_id, "recording_consent_id": own.consent_id,
        "idempotency_key": key, "source": "IOS_MIC", "recorded_at": "2026-10-15T09:00:00Z",
        "audio_ref": "voice.m4a"}, files={"file": ("voice.m4a", b"FAKE-AUDIO-" + key.encode(), "audio/mp4")})
    assert r.status_code == 201, r.text
    return h, r.json()["episode_id"]

def worker(app):
    return ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider, app.state.ai_client, backoff_seconds=0)

def test_source_delete_removes_memories_model_audio_and_survives_retry(app, client, session):
    own = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    other = seed_development_data(session, subject_name="Other", actor_name="Other")
    h, eid = capture(client, own, "ready")
    w = worker(app); w.run_once()
    review = client.get(f"/api/v1/episodes/{eid}/transcript-review", headers=h).json()
    assert client.patch(f"/api/v1/episodes/{eid}/transcript-review", headers=h, json={"transcript": review["transcript"]}).status_code == 200
    w.run_once(); w.run_once()
    h, kept = capture(client, own, "kept")
    session.expire_all(); key = session.get(Episode, eid).audio_object_key
    assert client.get(f"/api/v1/subjects/{own.subject_id}/memories", headers=h).json()["items"]
    assert client.delete(f"/api/v1/episodes/{eid}", headers={"Authorization": "Bearer " + other.actor_token}).status_code == 404
    response = client.delete(f"/api/v1/episodes/{eid}", headers=h)
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True, "cleanup_pending": False}
    schema = Path(__file__).resolve().parents[3] / "packages/contracts/schemas/recording-deletion-v1.schema.json"
    Draft202012Validator(json.loads(schema.read_text())).validate(response.json())
    assert not app.state.object_store.exists(key)
    assert client.get(f"/api/v1/episodes/{eid}/audio", headers=h).status_code == 404
    assert client.get(f"/api/v1/episodes/{eid}/transcript-review", headers=h).status_code == 404
    assert client.get(f"/api/v1/subjects/{own.subject_id}/memories", headers=h).json()["items"] == []
    assert [r["episode_id"] for r in client.get(f"/api/v1/subjects/{own.subject_id}/episodes", headers=h).json()["items"]] == [kept]
    assert eid not in {r["episode_id"] for r in client.get(f"/api/v1/workbench/subjects/{own.subject_id}/stories", headers=h).json()["items"]}
    assert not any(d["traits"] for d in client.get(f"/api/v1/subjects/{own.subject_id}/person-model", headers=h).json()["domains"])
    assert client.delete(f"/api/v1/episodes/{eid}", headers=h).json() == response.json()
    session.expire_all(); row = session.get(Episode, eid)
    assert not row.transcript and not row.stt_transcript and not row.audio_object_key
    assert all(not m.content and m.deleted_at for m in session.scalars(select(MemoryItem).where(MemoryItem.episode_id == eid)))
    assert all(not e.excerpt for e in session.scalars(select(Evidence).where(Evidence.episode_id == eid)))
    assert session.scalar(select(Job).where(Job.episode_id == eid)).state == "failed"

def test_delete_cancels_processing_and_private_storage_failure_is_retryable(app, client, session, monkeypatch):
    own = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    h, eid = capture(client, own, "queued")
    original = app.state.object_store.delete
    monkeypatch.setattr(app.state.object_store, "delete", lambda key: (_ for _ in ()).throw(RuntimeError("private-store-detail")))
    r = client.delete(f"/api/v1/episodes/{eid}", headers=h)
    assert r.status_code == 200 and r.json() == {"deleted": True, "cleanup_pending": True}
    assert "private-store-detail" not in r.text
    assert worker(app).run_once() is None
    pending = client.get(f"/api/v1/subjects/{own.subject_id}/episodes", headers=h).json()["items"]
    assert len(pending) == 1 and pending[0]["error_code"] == "SOURCE_DELETE_PENDING"
    assert "cleanup_object_key" not in json.dumps(pending)
    monkeypatch.setattr(app.state.object_store, "delete", original)
    assert client.delete(f"/api/v1/episodes/{eid}", headers=h).json() == {"deleted": True, "cleanup_pending": False}
    session.expire_all(); assert "cleanup_object_key" not in session.get(Episode, eid).capture_metadata


def test_delete_rejects_late_worker_publication(app, client, session):
    from app.repositories.jobs import JobRepository
    own = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    h, eid = capture(client, own, "late-worker")
    # Claim and snapshot just as a worker does before its external STT call.
    late = app.state.database.session()
    try:
        job = JobRepository(late).claim("late", lease_seconds=120)
        late.commit()
        ep = late.get(Episode, eid)
        assert client.delete(f"/api/v1/episodes/{eid}", headers=h).status_code == 200
        ep.transcript = "late result must never be published"
        assert not JobRepository(late).complete_stage(job, "late", ep)
        late.rollback()
    finally: late.close()
    session.expire_all()
    assert not session.get(Episode, eid).transcript
    assert worker(app).run_once() is None
