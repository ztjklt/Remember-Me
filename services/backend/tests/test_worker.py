"""The worker: one stage per tick, retry, and what a failure leaves behind.

The tests here drive the real repositories against the test database, and the
assertions are about what survives a failure as much as about the happy path —
"a failed AI step leaves the raw Episode intact and readable" is a definition of
done, not a nicety.

The last group is about the lease. A worker holds one while its stage runs, and
two things can go wrong with that: the stage can outlive the lease, and the lease
can be taken over while the stage is still going. Both end the same way — the
duplicate result must not be written — and the tests reproduce each one rather
than reasoning about it.
"""

import json
import logging
import time
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.ai_core import FakeAiCoreClient, HttpAiCoreClient
from app.errors import AiSchemaInvalid, AiUnavailable, SttUnavailable
from app.logging_config import JsonFormatter
from app.models import Episode, Evidence, Job, JobStage, JobState, MemoryItem, as_utc, utcnow
from app.seed import seed_development_data
from app.stt import FakeSttProvider, HttpSttProvider, Transcript
from app.worker import LeaseHeartbeat, ProcessingWorker

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
def uploaded(client: TestClient, auth, seeded, app) -> str:
    app.state.test_review_auth = auth
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
    worker = ProcessingWorker(
        app.state.database,
        app.state.object_store,
        stt or app.state.stt_provider,
        ai or app.state.ai_client,
        **options,
    )
    worker.test_app = app
    return worker


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
    """Test actor explicitly confirms STT through API; never a production shortcut."""
    results = []
    for _ in range(ticks):
        results.append(worker.run_once())
        review_pending(worker)
    return results


def review_pending(worker):
    with worker.test_app.state.database.session() as session:
        pending = [(ep.episode_id, ep.transcript) for ep in session.scalars(
            select(Episode).join(Job).where(Job.state == 'waiting'))]
    for episode_id, text in pending:
        with TestClient(worker.test_app) as client:
            r = client.patch(f'/api/v1/episodes/{episode_id}/transcript-review',
                headers=worker.test_app.state.test_review_auth, json={'transcript':text})
            assert r.status_code == 200, r.text


def test_one_tick_runs_one_stage_and_commits_it(worker, session, uploaded):
    assert worker.run_once() == uploaded

    episode = episode_of(session, uploaded)
    assert episode.transcript
    assert episode.stt_backend == "fake"
    assert episode.stt_model_version == "fake-stt-v1"

    job = job_of(session, uploaded)
    assert job.stage == str(JobStage.EXTRACT)
    assert job.state == str(JobState.WAITING)
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
    assert item["schema_version"] == "integration-contract-v0.2"

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
        review_pending(worker)

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
        review_pending(worker)

    job = job_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == 3
    assert Unreachable.calls == 3
    assert episode_of(session, uploaded).error_code == "AI_UNAVAILABLE"


@pytest.mark.parametrize(
    ("status_code", "error_code", "attempts"),
    [
        (413, "AI_FAILED", 1),
        (422, "AI_FAILED", 1),
        (502, "AI_FAILED", 1),
        (503, "AI_UNAVAILABLE", 3),
        (504, "AI_TIMEOUT", 3),
    ],
)
def test_ai_core_http_failure_persists_with_the_right_retry_budget(
    app, session, uploaded, monkeypatch, status_code, error_code, attempts
):
    calls = []

    def post(url, **kwargs):  # noqa: ANN001, ANN003, ANN202 - mirrors httpx.post
        calls.append((url, kwargs))
        return httpx.Response(status_code, text="provider error")

    monkeypatch.setattr(httpx, "post", post)
    ai = HttpAiCoreClient("http://ai-core.internal", "/process", 5.0)
    worker = build_worker(app, ai=ai, max_attempts=3)

    assert worker.run_once() == uploaded  # Transcription is committed first.
    assert episode_of(session, uploaded).transcript
    review_pending(worker)
    for _ in range(attempts):
        worker.run_once()

    job = job_of(session, uploaded)
    episode = episode_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == attempts
    assert job.last_error_code == error_code
    assert episode.status == "failed"
    assert episode.error_code == error_code
    assert episode.transcript  # The failed AI step cannot discard the source.
    assert app.state.object_store.get(episode.audio_object_key) == AUDIO
    assert len(calls) == attempts


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


@pytest.mark.parametrize(
    ("status_code", "error_code", "attempts"),
    [
        (413, "STT_FAILED", 1),
        (422, "STT_FAILED", 1),
        (502, "STT_FAILED", 1),
        (503, "STT_UNAVAILABLE", 3),
        (504, "STT_TIMEOUT", 3),
    ],
)
def test_an_stt_http_failure_persists_with_the_right_retry_budget(
    app, session, uploaded, monkeypatch, status_code, error_code, attempts
):
    """What the provider answers decides the budget, and the audio survives either way.

    The recording is stored before transcription is attempted (ADR-0001 D11), so
    a transcription that fails cannot lose it. The two rows assert that together
    because they are the same promise: the Episode records why, and the audio it
    could not read is still in the object store for the retry or the operator.
    """
    calls = []

    def post(url, **kwargs):  # noqa: ANN001, ANN003, ANN202 - mirrors httpx.post
        calls.append((url, kwargs))
        return httpx.Response(status_code, text="provider error")

    monkeypatch.setattr(httpx, "post", post)
    stt = HttpSttProvider("http://stt.internal", "/transcribe", 5.0)
    worker = build_worker(app, stt=stt, max_attempts=3)

    for _ in range(attempts):
        worker.run_once()

    job = job_of(session, uploaded)
    episode = episode_of(session, uploaded)
    assert job.state == str(JobState.FAILED)
    assert job.attempts == attempts
    assert job.last_error_code == error_code
    assert episode.status == "failed"
    assert episode.error_code == error_code
    assert episode.transcript is None
    assert app.state.object_store.get(episode.audio_object_key) == AUDIO
    # One request per attempt: the adapter does not retry underneath the job.
    assert len(calls) == attempts


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


# The lease, from the two directions it can go wrong. Both are about the same
# thing: a stage's result is written only while the worker that produced it still
# holds the work.


def _hand_the_work_to_another_worker(session, uploaded, usurper) -> str:  # noqa: ANN001
    """Expire the lease and let a second worker claim the job, mid-stage.

    This is the interleaving a slow provider call makes possible: the lease lapses
    while the stage runs, not between stages, and the work is claimed again before
    the first worker gets to write anything.
    """
    session.execute(
        update(Job)
        .where(Job.episode_id == uploaded)
        .values(lease_expires_at=utcnow() - timedelta(seconds=1))
    )
    session.commit()
    job_id = usurper._claim()
    assert job_id == job_of(session, uploaded).job_id
    return job_id


def test_a_stage_that_outlives_its_lease_commits_nothing(app, session, uploaded):
    """The hazard the commit-time compare-and-swap closes.

    The stage succeeds. It is the lease that lapses while it runs, which is what a
    slow provider does to a lease that was sized for a fast one — so the worker is
    holding a result for work that another worker is producing its own result for.
    """
    usurper = build_worker(app, owner="worker-that-took-over")

    class SlowProvider(FakeSttProvider):
        def transcribe(self, audio: bytes, content_type: str) -> Transcript:
            _hand_the_work_to_another_worker(session, uploaded, usurper)
            return Transcript(
                text="the transcript of the worker that lost the lease",
                backend="fake",
                model_version="fake-stt-v1",
            )

    slow = build_worker(app, stt=SlowProvider(), owner="slow-worker", lease_seconds=1)

    assert slow.run_once() == uploaded

    # Nothing the losing worker produced survived, the transcript included.
    assert episode_of(session, uploaded).transcript is None

    # The job is untouched and still owned by whoever holds the lease.
    job = job_of(session, uploaded)
    assert job.stage == str(JobStage.TRANSCRIBE)
    assert job.state == str(JobState.RUNNING)
    assert job.lease_owner == "worker-that-took-over"

    # And the work is not lost: the worker that holds it can finish it.
    assert usurper._run_stage(job.job_id) == uploaded
    assert episode_of(session, uploaded).transcript.startswith("[fake-stt]")


def test_a_failure_after_the_lease_lapsed_is_not_recorded(app, session, uploaded, monkeypatch):
    """A retry decision is a lease release, so it goes through the same swap.

    The pre-check is forced to answer yes here, because that is what a read taken
    a moment earlier would have said: the point of the test is the write, which is
    the only place the answer is still true when it is used.
    """
    usurper = build_worker(app, owner="worker-that-took-over")

    class FailingProvider(FakeSttProvider):
        def transcribe(self, audio: bytes, content_type: str) -> Transcript:
            _hand_the_work_to_another_worker(session, uploaded, usurper)
            raise SttUnavailable("no provider answered")

    slow = build_worker(
        app,
        stt=FailingProvider(),
        owner="slow-worker",
        lease_seconds=1,
        backoff_seconds=3600,
    )
    monkeypatch.setattr(slow, "_still_holds_the_lease", lambda job: True)

    slow.run_once()

    # Neither the retry nor the give-up was this worker's to record.
    job = job_of(session, uploaded)
    assert job.state == str(JobState.RUNNING)
    assert job.lease_owner == "worker-that-took-over"
    assert job.last_error_code is None
    assert job.attempts == 2, "the claim that took the work over is the only attempt"

    episode = episode_of(session, uploaded)
    assert episode.error_code is None
    assert episode.status == "transcribing"


def test_the_heartbeat_renews_the_lease_while_a_stage_runs(app, session, uploaded):
    """Renewal is what stops a slow stage from being executed twice at all."""
    worker = build_worker(app, owner="renewing-worker", lease_seconds=8)
    job_id = worker._claim()
    claimed_expiry = as_utc(job_of(session, uploaded).lease_expires_at)

    heartbeat = LeaseHeartbeat(
        app.state.database,
        job_id,
        "renewing-worker",
        lease_seconds=8,
        interval_seconds=0.05,
    )
    heartbeat.start()
    time.sleep(0.3)
    heartbeat.stop()

    assert as_utc(job_of(session, uploaded).lease_expires_at) > claimed_expiry


def test_the_heartbeat_gives_up_a_lease_it_no_longer_holds(app, session, uploaded):
    """Renewing a lease this process does not hold would extend a claim it lost."""
    worker = build_worker(app, owner="renewing-worker")
    job_id = worker._claim()

    heartbeat = LeaseHeartbeat(
        app.state.database,
        job_id,
        "renewing-worker",
        lease_seconds=60,
        interval_seconds=0.05,
    )
    heartbeat.start()
    time.sleep(0.15)
    assert heartbeat.alive, "the heartbeat must still be renewing a lease it holds"

    session.execute(
        update(Job).where(Job.job_id == job_id).values(lease_owner="someone-else")
    )
    session.commit()

    deadline = time.monotonic() + 5
    while heartbeat.alive and time.monotonic() < deadline:
        time.sleep(0.02)
    heartbeat.stop()

    assert not heartbeat.alive


@pytest.fixture
def worker_log():
    """The worker's own output, formatted as it is written.

    `trace_id` is attached by the formatter from a context variable, so it has to
    be read while the record is emitted — inspecting the LogRecord afterwards
    would always find it cleared. This is also the shape that reaches disk, which
    is what the "no transcript in the logs" rule is about.
    """

    class Capture(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.payloads: list[dict] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.payloads.append(json.loads(JsonFormatter().format(record)))

    handler = Capture()
    logger = logging.getLogger("app.worker")
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler.payloads
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def test_a_completed_stage_is_logged_with_what_produced_it(worker, uploaded, worker_log):
    """ADR-0001 D13 promises the transitions, the durations, and the versions.

    A run that succeeds used to log nothing at all, which left the question worth
    asking — "the Episode is stuck, what is the worker doing?" — with no answer in
    the worker's own output.
    """
    advance(worker)

    completed = [p for p in worker_log if p["message"] == "stage.completed"]

    assert [p["stage"] for p in completed] == ["transcribe", "extract", "model"]
    # The status names the stage that just ran, which is what a poller sees.
    assert [p["status"] for p in completed] == ["transcribing", "extracting", "ready"]
    assert {p["episode_id"] for p in completed} == {uploaded}
    assert all(p["job_id"] and p["duration_ms"] >= 0 for p in completed)

    # Each stage names its own producer. The transcript is still on the row when
    # the extract stage runs, so reading "whichever version is set" would report
    # the transcriber's model as the one that extracted the memories.
    assert (completed[0]["provider"], completed[0]["model_version"]) == (
        "fake",
        "fake-stt-v1",
    )
    assert completed[1]["model_version"] == "fake-ai-v1"
    assert completed[2]["model_version"] == "fake-ai-v1"


def test_a_worker_line_carries_the_episodes_trace_id(worker, session, uploaded, worker_log):
    """`infra/deployment.md` promises the two processes' logs are matchable.

    That is the whole of the troubleshooting story: the client has an
    `episode_id`, the log lines carry a `trace_id`, and the status endpoint is
    what converts one into the other.
    """
    trace_id = episode_of(session, uploaded).trace_id

    advance(worker)

    completed = [p for p in worker_log if p["message"] == "stage.completed"]
    assert completed, "the fixture must produce output to check"
    assert {p["trace_id"] for p in completed} == {trace_id}


def test_a_failed_stage_is_findable_from_the_episode(app, session, uploaded, worker_log):
    class Unreachable(FakeAiCoreClient):
        def process(self, payload):  # noqa: ANN001, ANN201
            raise AiUnavailable("AI Core is unreachable")

    trace_id = episode_of(session, uploaded).trace_id

    advance(build_worker(app, ai=Unreachable()))

    failed = [p for p in worker_log if p["message"] == "stage.failed"]
    assert failed, "a stage that failed must say so"
    assert {p["error_code"] for p in failed} == {"AI_UNAVAILABLE"}
    assert {p["trace_id"] for p in failed} == {trace_id}


def test_the_worker_logs_never_carry_the_transcript(worker, session, uploaded, worker_log):
    """A transcript is the subject's speech; a log line is written to disk."""
    advance(worker)

    transcript = episode_of(session, uploaded).transcript
    assert transcript, "the fixture must actually produce a transcript"

    written = "\n".join(json.dumps(payload) for payload in worker_log)
    assert transcript not in written
