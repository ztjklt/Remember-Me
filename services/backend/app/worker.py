"""The processing worker.

One tick claims one job and runs one stage of it, then commits. The next tick
picks the Episode up again for the following stage. That is slower than running
the whole pipeline in one pass and it is the point: each transition is committed
on its own, so an Episode's progress is visible from outside the process while it
happens, and a crash between stages loses at most the stage in flight — the
Episode row and its audio are already durable (Issue #1's definition of done).

The worker runs as its own process:

    uv run python -m app.worker

It is not started by the API process. A stage that blocks for thirty seconds
would otherwise occupy a web worker, and Phase 1 has no reason to couple the two
lifetimes.

**Running more than one worker is safe, and that is what the lease is for.** A
worker claims a job, renews the claim while its stage runs, and commits the
result only while it still holds it. Both halves matter and they answer different
halves of one hazard: renewal stops a slow stage from being executed twice in the
first place, and the commit-time compare-and-swap makes a duplicate commit
impossible even when renewal fails — which it can, because a heartbeat is a
best-effort thread and a lease can lapse between two of them.
"""

import logging
import sys
import threading
import time
from uuid import uuid4

from .ai_core import AiCoreClient, build_ai_client
from .config import Settings, get_settings
from .contracts import AICoreInput
from .db import Database
from .errors import (
    AppError,
    AudioUnavailable,
    SttEmptyTranscript,
    SttUnavailable,
)
from .models import Episode, JobStage, JobState
from .person_model import rebuild_person_model
from .repositories.episodes import EpisodeRepository
from .repositories.jobs import STAGE_STATUS, JobRepository
from .repositories.memory import MemoryRepository
from .stt import SttProvider, build_stt_provider
from .storage import build_object_store
from .storage.base import ObjectStore

logger = logging.getLogger("app.worker")


class UnexpectedFailure(AppError):
    """A raised exception that is not part of the taxonomy.

    Retried: an unexpected fault is far more often transient infrastructure than a
    deterministic refusal. It is bounded like any other retryable failure, so a
    stage that dies on a bug still converges on `failed` rather than looping.
    """

    code = "INTERNAL"
    http_status = 500
    retryable = True


class LeaseHeartbeat:
    """Renews a worker's lease for as long as its stage is running.

    A lease that lapses while a stage is in flight hands the same work to a second
    worker, and stages outlive leases as a matter of course: a recording long
    enough to be worth transcribing is slower to transcribe than the default
    lease. Renewal is what keeps that from happening — and it runs on its own
    thread because a stage is one blocking provider call, with no point inside it
    at which the worker could renew on the way past.

    It is best-effort by construction. The commit-time compare-and-swap in
    `JobRepository`, not this thread, is what makes a double commit impossible: a
    heartbeat can always be the one that did not happen, so a lease that is lost
    anyway costs duplicate work rather than a duplicate result.
    """

    def __init__(
        self,
        database: Database,
        job_id: str,
        owner: str,
        *,
        lease_seconds: int,
        interval_seconds: float | None = None,
    ) -> None:
        self.database = database
        self.job_id = job_id
        self.owner = owner
        self.lease_seconds = lease_seconds
        # A third of the lease, so two renewals can fail before the work is at
        # risk. The floor keeps a very short lease from spinning.
        self.interval_seconds = interval_seconds or max(1.0, lease_seconds / 3)
        self._stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._renew_until_stopped, name="lease-heartbeat", daemon=True
        )

    def start(self) -> "LeaseHeartbeat":
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop renewing. Returns without waiting indefinitely for the thread."""
        self._stopped.set()
        # A renewal blocked on an unreachable database must not hold the tick
        # open. The thread is a daemon, and a renewal that lands late is refused
        # by the lease owner it no longer matches.
        self._thread.join(timeout=self.interval_seconds)

    def __enter__(self) -> "LeaseHeartbeat":
        return self.start()

    def __exit__(self, *_exception: object) -> None:
        self.stop()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    def _renew_until_stopped(self) -> None:
        while not self._stopped.wait(self.interval_seconds):
            if not self._renew_once():
                # The lease is somebody else's now. Renewing it further would
                # extend a claim this worker does not have; the stage's commit
                # will be refused either way.
                return

    def _renew_once(self) -> bool:
        session = self.database.session()
        try:
            held = JobRepository(session).renew_lease(
                self.job_id, self.owner, lease_seconds=self.lease_seconds
            )
            session.commit()
            if not held:
                logger.warning(
                    "lease.renewal_refused",
                    extra={"extra_fields": {"job_id": self.job_id, "owner": self.owner}},
                )
            return held
        except Exception as error:  # noqa: BLE001 - renewal must not kill the stage
            # One failed renewal is not a lost lease: the attempt is logged and
            # the next interval tries again.
            logger.warning(
                "lease.renewal_failed",
                extra={
                    "extra_fields": {
                        "job_id": self.job_id,
                        "owner": self.owner,
                        "error": str(error),
                    }
                },
            )
            return True
        finally:
            session.close()


class ProcessingWorker:
    def __init__(
        self,
        database: Database,
        object_store: ObjectStore,
        stt: SttProvider,
        ai: AiCoreClient,
        *,
        max_attempts: int = 3,
        backoff_seconds: int = 5,
        lease_seconds: int = 60,
        owner: str | None = None,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        self.database = database
        self.object_store = object_store
        self.stt = stt
        self.ai = ai
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.lease_seconds = lease_seconds
        # Derived from the lease unless a caller says otherwise, which is what
        # lets a test observe renewal without waiting a third of a minute.
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        # Identifies this process in the lease, so a worker can tell its own claim
        # from one another worker has taken over.
        self.owner = owner or f"worker-{uuid4().hex[:8]}"

    def run_once(self) -> str | None:
        """Run one stage of one job. Returns the Episode id, or None if idle."""
        job_id = self._claim()
        if job_id is None:
            return None
        try:
            return self._run_stage(job_id)
        except AppError as error:
            logger.warning(
                "stage.failed",
                extra={
                    "extra_fields": {
                        "job_id": job_id,
                        "error_code": error.code,
                        "error_message": error.message,
                    }
                },
            )
            self._record_failure(job_id, error)
        except Exception as error:  # noqa: BLE001 - a stage must not kill the worker
            logger.exception("stage.crashed", extra={"extra_fields": {"job_id": job_id}})
            self._record_failure(
                job_id, UnexpectedFailure(str(error) or type(error).__name__)
            )
        return None

    def _claim(self) -> str | None:
        """Take the lease on one job and commit it immediately, with the status.

        Committed on its own, in its own transaction, for two reasons. The status
        it records is the stage being worked on, so it has to be visible while
        the work is in flight rather than at the end of it. And a stage that then
        fails and rolls back must not also undo the attempt it just consumed —
        otherwise a stage that fails before writing anything would retry forever.
        """
        session = self.database.session()
        try:
            job = JobRepository(session).claim(self.owner, lease_seconds=self.lease_seconds)
            if job is None:
                return None
            episode = EpisodeRepository(session).require(job.episode_id)
            episode.status = str(STAGE_STATUS[JobStage(job.stage)])
            session.commit()
        finally:
            session.close()
        return job.job_id

    def _run_stage(self, job_id: str) -> str:
        session = self.database.session()
        try:
            jobs = JobRepository(session)
            episodes = EpisodeRepository(session)
            job = jobs.get(job_id)
            if job is None:
                raise UnexpectedFailure(f"Job {job_id} disappeared after it was claimed")
            episode = episodes.require(job.episode_id)
            # Captured before any rollback, because an expired Episode object
            # cannot be read back for its id without starting a new transaction.
            episode_id = episode.episode_id

            if not self._still_holds_the_lease(job):
                # The lease expired before the stage started and someone else owns
                # this work now. Doing the stage anyway would write a second
                # result over theirs.
                logger.warning(
                    "lease.lost",
                    extra={"extra_fields": {"job_id": job_id, "owner": self.owner}},
                )
                return episode_id

            stage = JobStage(job.stage)
            with self._heartbeat(job_id):
                if stage is JobStage.TRANSCRIBE:
                    self._transcribe(episode)
                elif stage is JobStage.EXTRACT:
                    self._extract(session, episode)
                else:
                    self._model(session, episode)

                if not jobs.complete_stage(job, self.owner, episode):
                    # The lease lapsed while the stage ran and another worker has
                    # the work — it may already have committed a result for it.
                    # Rolling back discards this stage's writes, the transcript
                    # included, rather than leaving a second one behind.
                    session.rollback()
                    logger.warning(
                        "lease.lost_at_commit",
                        extra={"extra_fields": {"job_id": job_id, "owner": self.owner}},
                    )
                    return episode_id
                session.commit()
            return episode_id
        finally:
            session.close()

    def _heartbeat(self, job_id: str) -> LeaseHeartbeat:
        return LeaseHeartbeat(
            self.database,
            job_id,
            self.owner,
            lease_seconds=self.lease_seconds,
            interval_seconds=self.heartbeat_interval_seconds,
        )

    def _still_holds_the_lease(self, job) -> bool:  # type: ignore[no-untyped-def]
        """A cheap pre-check, not the guarantee.

        It answers "is this worth starting at all" from the row the worker already
        read. What makes a duplicate result impossible is the compare-and-swap the
        commit goes through, because this check cannot see a lease that lapses
        after it runs.
        """
        return (
            job.state == str(JobState.RUNNING)
            and job.lease_owner == self.owner
            and job.lease_expires_at is not None
        )

    def _transcribe(self, episode: Episode) -> None:
        try:
            audio = self.object_store.get(episode.audio_object_key)
        except Exception as error:  # noqa: BLE001 - any store failure is one code
            raise AudioUnavailable(
                f"The audio for episode {episode.episode_id} could not be read "
                f"from object storage: {error}"
            ) from error

        try:
            transcript = self.stt.transcribe(audio, episode.audio_content_type)
        except AppError:
            raise
        except Exception as error:  # noqa: BLE001 - a provider failure is one code
            raise SttUnavailable(f"The speech-to-text provider failed: {error}") from error

        if not transcript.text.strip():
            raise SttEmptyTranscript(
                f"Transcription of episode {episode.episode_id} produced no text"
            )

        episode.transcript = transcript.text
        episode.stt_backend = transcript.backend
        episode.stt_model_version = transcript.model_version

    def _extract(self, session, episode: Episode) -> None:  # type: ignore[no-untyped-def]
        """Ask AI Core to turn the transcript into memories, and store the result.

        Between the call and the write there is one transaction, so an AI Core
        answer that fails validation leaves the Episode exactly as it was: with a
        transcript, no result, and a status saying which stage it stopped at.
        """
        if not episode.transcript:
            raise UnexpectedFailure(
                f"Episode {episode.episode_id} reached the extract stage with no transcript"
            )

        payload = AICoreInput(
            episode_id=episode.episode_id,
            subject_id=episode.subject_id,
            transcript=episode.transcript,
            # Derived from the record, never from the request: what AI Core is
            # updating is the subject's latest ready model, and a client that
            # could name its own baseline could name a wrong one.
            existing_model_version=EpisodeRepository(session).latest_model_version(
                episode.subject_id
            ),
            trace_id=episode.trace_id,
        )
        output = self.ai.process(payload)
        MemoryRepository(session).store_result(episode, output)

    def _model(self, session, episode: Episode) -> None:  # type: ignore[no-untyped-def]
        """The last stage: an Episode becomes ready only past this point.

        `ready` is reachable only after a stored extraction result. On this
        isolated branch the stage also materializes a conservative seven-domain
        preview from the Actor's evidence-linked Memory rows. This is not a
        generative personality synthesis or the future temporal graph.
        """
        if episode.model_version is None:
            raise UnexpectedFailure(
                f"Episode {episode.episode_id} reached the model stage with no result"
            )
        rebuild_person_model(
            session, subject_id=episode.subject_id, actor_id=episode.actor_id
        )

    def _record_failure(self, job_id: str, error: AppError) -> None:
        """Retry the stage or give up, in its own transaction.

        This runs after the failed stage's session is closed, so the stage's
        uncommitted writes are gone and this transaction writes only the outcome.
        The outcome is a release of the lease like any other, so it goes through
        the same compare-and-swap: a worker whose lease lapsed mid-stage does not
        get to decide what happens to work that is no longer its own.
        """
        session = self.database.session()
        try:
            jobs = JobRepository(session)
            job = jobs.get(job_id)
            if job is None or not self._still_holds_the_lease(job):
                return
            episode = EpisodeRepository(session).require(job.episode_id)

            if error.retryable and job.attempts < self.max_attempts:
                landed = jobs.reschedule(
                    job, self.owner, episode, error, delay_seconds=self.backoff_seconds
                )
            else:
                landed = jobs.give_up(job, self.owner, episode, error)

            if not landed:
                session.rollback()
                logger.warning(
                    "lease.lost_at_failure",
                    extra={"extra_fields": {"job_id": job_id, "owner": self.owner}},
                )
                return
            session.commit()
        finally:
            session.close()


def build_worker(database: Database, settings: Settings) -> ProcessingWorker:
    return ProcessingWorker(
        database,
        build_object_store(settings),
        build_stt_provider(settings),
        build_ai_client(settings),
        max_attempts=settings.job_max_attempts,
        backoff_seconds=settings.job_retry_backoff_seconds,
        lease_seconds=settings.job_lease_seconds,
    )


def main() -> int:
    settings = get_settings()
    from .logging_config import configure_logging

    configure_logging(settings.log_level)

    database = Database(settings.database_url)
    worker = build_worker(database, settings)
    logger.info(
        "worker.started",
        extra={
            "extra_fields": {
                "owner": worker.owner,
                "stt_backend": settings.stt_backend,
                "ai_backend": settings.ai_backend,
            }
        },
    )
    try:
        while True:
            if worker.run_once() is None:
                time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("worker.stopped", extra={"extra_fields": {"owner": worker.owner}})
        return 0
    finally:
        database.dispose()


if __name__ == "__main__":
    sys.exit(main())
