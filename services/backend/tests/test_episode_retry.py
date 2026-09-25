from app.models import Episode, Job, JobStage, JobState
from app.seed import seed_development_data


def test_retry_requeues_failed_stage_on_same_episode_and_requires_consent(client, session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    auth = {"Authorization": f"Bearer {seeded.actor_token}"}
    created = client.post("/api/v1/episodes", headers=auth, data={
        "subject_id": seeded.subject_id, "recording_consent_id": seeded.consent_id,
        "source": "IMPORT", "recorded_at": "2026-09-25T08:00:00Z",
        "audio_ref": "recording.m4a", "idempotency_key": "retry-test",
    }, files={"file": ("recording.m4a", b"audio", "audio/mp4")})
    assert created.status_code == 201
    episode_id = created.json()["episode_id"]
    episode = session.get(Episode, episode_id)
    job = session.query(Job).filter_by(episode_id=episode_id).one()
    episode.status = "failed"
    episode.error_code = "AI_UNAVAILABLE"
    job.state = str(JobState.FAILED)
    job.stage = str(JobStage.EXTRACT)
    job.attempts = 3
    session.commit()

    retried = client.post(f"/api/v1/episodes/{episode_id}/retry", headers=auth)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "extracting"
    session.expire_all()
    assert session.get(Job, job.job_id).state == "queued"
    assert session.get(Job, job.job_id).attempts == 0
    assert session.get(Episode, episode_id).error_code is None
    assert client.post(f"/api/v1/episodes/{episode_id}/retry", headers=auth).status_code == 422

    episode = session.get(Episode, episode_id)
    job = session.get(Job, job.job_id)
    episode.status = "failed"
    job.state = str(JobState.FAILED)
    session.commit()
    client.post(f"/api/v1/consents/{seeded.consent_id}/revoke", headers=auth)
    assert client.post(f"/api/v1/episodes/{episode_id}/retry", headers=auth).status_code == 403
