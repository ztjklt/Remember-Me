"""The worker: one stage per tick, retry, and what a failure leaves behind.

The tests here drive the real repositories against the test database, and the
assertions are about what survives a failure as much as about the happy path —
"a failed AI step leaves the raw Episode intact and readable" is a definition of
done, not a nicety.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.ai_core import FakeAiCoreClient
from app.errors import AiSchemaInvalid, AiUnavailable, SttUnavailable
from app.models import Episode, Evidence, Job, JobStage, JobState, MemoryItem, as_utc, utcnow
from app.seed import seed_development_data
from app.stt import FakeSttProvider, Transcript
from app.worker import ProcessingWorker

AUDIO = b"RIFF\x00\x00\x00\x00WAVEfmt "

CAPTURE_FIELDS = {
    "source": "ANDROID_MIC",
    "recorded_at": "2026-09-21T09:30:00+00:00",
    "audio_ref": "walk-in-the-park.m4a",
    "idempotency_key": "capture-0001",
}


@pytest.fixture
def seeded(session):
    return seed_development_data(session, subject_name="Ada", actor_name="Ada")


@pytest.fixture
def auth(seeded) -> dict[str, str]:
    return {"Authorization": f"Bearer {seeded.actor_token}"}


@pytest.fixture
def uploaded(client: TestClient, auth, seeded) -> str:
    response = client.post(
        "/api/v1/episodes",
        headers=auth,
        data={
            "subject_id": seeded.subject_id,
            "recording_consent_id": seeded.consent_id,
            **CAPTURE_FIELDS,
        },
        files={"file": ("walk-in-the-park.m4a", AUDIO, "audio/mp4")},
    )
    assert response.status_code == 201, response.text
    return response.json()["episode_id"]


def build_worker(app, *, stt=None, ai=None, **overrides) -> ProcessingWorker:  # noqa: ANN001
    """A worker over the application's own database and object store."""
    options: dict[str, object] = {
        "max_attempts": 3,
        "backoff_seconds": 0,
        "lease_seconds": 60,
        "owner": "test-worker",
    }
    options.update(overrides)
    return ProcessingWorker(
        app.state.database,
        app.state.object_store,
        stt or app.state.stt_provider,
        ai or app.state.ai_client,
        **options,
    )


@pytest.fixture
def worker(app) -> ProcessingWorker:
    return build_worker(app)


def status_of(database, episode_id: str) -> str:  # noqa: ANN001
    """The status as a client would see it: read from a separate session."""
    session = database.session()
    try:
        return session.get(Episode, episode_id).status
    finally:
        session.close()


def episode_of(session, episode_id: str) -> Episode:
    """The Episode, reloaded: the worker commits through sessions of its own."""
    session.expire_all()
    return session.get(Episode, episode_id)


def job_of(session, episode_id: str) -> Job:
    session.expire_all()
    return session.scalars(select(Job).where(Job.episode_id == episode_id)).one()


def advance(worker: ProcessingWorker, *, ticks: int = 6) -> list[str | None]:
    """Run ticks until the queue is empty."""
    return [worker.run_once() for _ in range(ticks)]


def test_one_tick_runs_one_stage_and_commits_it(worker, session, uploaded):
    assert worker.run_once() == uploaded

    episode = episode_of(session, uploaded)
    assert episode.transcript
    assert episode.stt_backend == "fake"
    assert episode.stt_model_version == "fake-stt-v1"

    job = job_of(session, uploaded)
    assert job.stage == str(JobStage.EXTRACT)
    assert job.state == str(JobState.QUEUED)
    # The budget is per stage, so the stage that just succeeded hands the next
    # one a full set of attempts.
    assert job.attempts == 0
    # The lease is released between stages, so nothing holds the Episode while
    # it waits for the next tick.
    assert job.lease_owner is None
    assert job.lease_expires_at is None


def test_processing_runs_to_a_readable_result(client, worker, session, uploaded, auth):
    advance(worker)

    status = client.get(f"/api/v1/episodes/{uploaded}", headers=auth)
    assert status.status_code == 200
    assert status.json()["status"] == "ready"

    result = client.get(f"/api/v1/episodes/{uploaded}/result", headers=auth)
    assert result.status_code == 200, result.text
    body = result.json()

    assert body["episode_id"] == uploaded
    assert body["status"] == "ready"
    assert body["model_version"] == "fake-ai-v1"
    assert len(body["memory_items"]) == 1

    item = body["memory_items"][0]
    assert set(item) == {
        "memory_type",
        "content",
        "source_type",
        "evidence_ids",
        "confidence",
        "model_version",
        "prompt_version",
        "schema_version",
    }
    assert item["memory_type"] == "EVENT"
    # Nothing was actually heard, so the item is labelled as an inference rather
    # than as something the subject said.
    assert item["source_type"] == "AI_INFERENCE"
    assert item["model_version"] == "fake-ai-v1"
    assert item["prompt_version"] == "fake-prompt-v1"
    assert item["schema_version"] == "integration-contract-v0.1"

    # The evidence a memory rests on was stored, and the id resolves.
    evidence = session.scalars(
        select(Evidence).where(Evidence.episode_id == uploaded)
    ).all()
    assert [row.evidence_id for row in evidence] == item["evidence_ids"]
    assert evidence[0].source_type == "SUBJECT"
    assert evidence[0].excerpt == episode_of(session, uploaded).transcript

    assert session.scalar(
        select(MemoryItem).where(MemoryItem.episode_id == uploaded)
    ).ordinal == 0


def test_each_stage_shows_the_status_of_the_work_in_flight(app, client, session, uploaded, auth):
    """A client polling during a stage sees that stage, not the previous one.

    The probe reads through its own session, so what it observes is what was
    committed — the same thing an HTTP client would get.
    """

    class Probe:
        def __init__(self) -> None:
            self.during: dict[str, str] = {}

        def transcribe(self, audio: bytes, content_type: str) -> Transcript:
            self.during["transcribe"] = status_of(app.state.database, uploaded)
            return FakeSttProvider().transcribe(audio, content_type)

        def process(self, payload):  # noqa: ANN001, ANN201 - mirrors AiCoreClient
            self.during["extract"] = status_of(app.state.database, uploaded)
            return FakeAiCoreClient().process(payload)

    probe = Probe()
    worker = build_worker(app, stt=probe, ai=probe)

    seen = [status_of(app.state.database, uploaded)]
    for _ in range(3):
        worker.run_once()
        seen.append(status_of(app.state.database, uploaded))

    assert probe.during == {"transcribe": "transcribing", "extract": "extracting"}
    assert seen == ["uploaded", "transcribing", "extracting", "ready"]


def test_the_transcript_is_kept_when_a_later_stage_fails(client, session, uploaded, auth, app):
    class InvalidOutput(FakeAiCoreClient):
        def process(self, payload):  # noqa: ANN001, ANN201
            raise AiSchemaInvalid("AI Core sent something that is not an aiCoreOutput")

    worker = build_worker(app, ai=InvalidOutput())

    advance(worker)

    episode = episode_of(session, uploaded)
    assert episode.status == "failed"
    assert episode.error_code == "AI_SCHEMA_INVALID"
    assert episode.transcript  # the transcription survived
    assert episode.model_version is None

    # The Episode is still readable, and says what went wrong rather than
    # disappearing.
    status = client.get(f"/api/v1/episodes/{uploaded}", headers=auth)
    assert status.status_code == 200
    assert status.json()["status"] == "failed"
    assert status.json()["error_code"] == "AI_SCHEMA_INVALID"

    # And the audio is still where it was.
    assert app.state.object_store.get(episode.audio_object_key) == AUDIO


def test_a_deterministic_failure_is_not_retried(app, session, uploaded):
    class AlwaysInvalid(FakeAiCoreClient):
        calls = 0

        def process(self, payload):  # noqa: ANN001, ANN201
            type(self).calls += 1
            raise AiSchemaInvalid("still not an aiCoreOutput")

    worker = build_worker(app, ai=AlwaysInvalid())

    advance(worker)

    job = job_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == 1, "a failure that cannot improve is not retried"
    assert AlwaysInvalid.calls == 1
    assert job.last_error_code == "AI_SCHEMA_INVALID"


def test_a_retryable_failure_is_retried_until_the_budget_is_gone(app, session, uploaded):
    class Unreachable(FakeAiCoreClient):
        calls = 0

        def process(self, payload):  # noqa: ANN001, ANN201
            type(self).calls += 1
            raise AiUnavailable("AI Core is unreachable")

    worker = build_worker(app, ai=Unreachable(), max_attempts=3)

    for _ in range(8):
        worker.run_once()

    job = job_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == 3
    assert Unreachable.calls == 3
    assert episode_of(session, uploaded).error_code == "AI_UNAVAILABLE"


def test_a_retryable_failure_leaves_the_episode_on_the_stage_it_is_stuck_on(
    app, session, uploaded
):
    class Unavailable(FakeSttProvider):
        def transcribe(self, audio: bytes, content_type: str) -> Transcript:
            raise SttUnavailable("no provider answered")

    worker = build_worker(app, stt=Unavailable(), backoff_seconds=3600)

    worker.run_once()

    episode = episode_of(session, uploaded)
    # Still transcribing, with the reason: the attempt failed, the work did not
    # end.
    assert episode.status == "transcribing"
    assert episode.error_code == "STT_UNAVAILABLE"
    assert episode.transcript is None

    job = job_of(session, uploaded)
    assert job.state == str(JobState.QUEUED)
    assert job.attempts == 1
    # Waiting, not retrying immediately: backoff is scheduled, not ignored.
    assert as_utc(job.available_at) > utcnow()


def test_a_missing_audio_object_is_named_as_such(app, session, uploaded):
    """A storage problem must not be reported as a transcription problem."""
    app.state.object_store._objects.clear()
    worker = build_worker(app, max_attempts=2)

    advance(worker)

    job = job_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.last_error_code == "AUDIO_UNAVAILABLE"
    assert episode_of(session, uploaded).error_code == "AUDIO_UNAVAILABLE"


def test_an_empty_transcript_ends_the_episode_without_retrying(app, session, uploaded):
    class Silent(FakeSttProvider):
        def transcribe(self, audio: bytes, content_type: str) -> Transcript:
            return Transcript(text="   ", backend="fake", model_version="fake-stt-v1")

    worker = build_worker(app, stt=Silent())

    advance(worker)

    job = job_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == 1
    assert job.last_error_code == "STT_EMPTY_TRANSCRIPT"


def test_a_lease_that_expires_returns_the_work_to_any_worker(app, session, uploaded):
    """A worker that dies mid-stage must not strand an Episode."""
    # Claimed and then abandoned: the process is gone, so nothing releases it.
    abandoned = build_worker(app, owner="worker-that-died")
    assert abandoned._claim() == job_of(session, uploaded).job_id
    assert job_of(session, uploaded).state == str(JobState.RUNNING)

    # The lease runs out with nothing to release it.
    session.execute(
        update(Job)
        .where(Job.episode_id == uploaded)
        .values(lease_expires_at=utcnow() - timedelta(seconds=1))
    )
    session.commit()

    survivor = build_worker(app, owner="worker-that-lived")
    assert survivor._claim() == job_of(session, uploaded).job_id
    assert job_of(session, uploaded).attempts == 2, "the recovery is a second attempt"

    # And the recovered work can be finished by whoever picked it up.
    assert survivor._run_stage(job_of(session, uploaded).job_id) == uploaded
    assert episode_of(session, uploaded).transcript


def test_a_worker_that_lost_its_lease_abandons_the_stage(app, session, uploaded):
    """The guard against two workers writing the same stage's result."""
    slow = build_worker(app, owner="slow-worker", lease_seconds=0)
    job_id = slow._claim()
    assert job_id == job_of(session, uploaded).job_id

    # A second worker takes the work over — which a zero-second lease allows.
    quick = build_worker(app, owner="quick-worker")
    assert quick.run_once() == uploaded
    transcript = episode_of(session, uploaded).transcript

    # The first worker now finishes its stage. It must change nothing.
    assert slow._run_stage(job_id) == uploaded
    assert episode_of(session, uploaded).transcript == transcript
    assert job_of(session, uploaded).lease_owner is None


def test_nothing_runs_when_the_queue_is_empty(worker):
    assert worker.run_once() is None