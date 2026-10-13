"""The job table as a queue.

A row in `jobs` is the unit of processing work, and claiming one is what makes a
worker the only process running that stage (ADR-0001 D8). There is no broker:
`enqueue` writes a queued row, `claim` takes a lease on one, and a lease that
expires puts the work back in reach of any worker, which is how a worker that dies
mid-stage is recovered rather than leaving an Episode stuck forever.

Claiming is a compare-and-swap rather than a `SELECT ... FOR UPDATE SKIP LOCKED`:
read the first eligible job, then update it *only if it is still eligible*. If
another worker won the row in between, the update matches nothing and this tick
does no work — a tick that finds nothing is free, and the next one is along
shortly, whereas a worker that took a row twice would run a stage twice.

**Releasing a lease is a compare-and-swap too.** Checking "do I still hold this
job?" with a read and then writing the result is a check-then-act: a lease that
expires while a long stage runs passes the read and the write lands anyway, which
is exactly how two workers end up committing the same stage. Every transition out
of a stage therefore *writes* the lease condition into the `UPDATE` — same owner,
same running state, and not yet expired — and the transaction is rolled back
whole when the condition fails. A stage whose lease was lost therefore commits
nothing at all, not even the transcript it produced.
"""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..errors import AppError
from ..models import Episode, EpisodeStatus, Job, JobStage, JobState, utcnow

# The status an Episode shows while a stage is running. Written in the same
# transaction as the job's stage, so the two never disagree.
STAGE_STATUS = {
    JobStage.TRANSCRIBE: EpisodeStatus.TRANSCRIBING,
    JobStage.EXTRACT: EpisodeStatus.EXTRACTING,
    JobStage.MODEL: EpisodeStatus.MODELING,
}

# None ends the pipeline.
NEXT_STAGE = {
    JobStage.TRANSCRIBE: JobStage.EXTRACT,
    JobStage.EXTRACT: JobStage.MODEL,
    JobStage.MODEL: None,
}


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, job: Job) -> Job:
        self.session.add(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.session.get(Job, job_id)

    def for_episode(self, episode_id: str) -> Job | None:
        return self.session.scalars(
            select(Job).where(Job.episode_id == episode_id)
        ).one_or_none()

    def enqueue(self, episode_id: str) -> Job:
        """Queue the transcription of a freshly uploaded Episode."""
        return self.add(
            Job(
                job_id=f"job_{uuid4().hex[:16]}",
                episode_id=episode_id,
                state=str(JobState.QUEUED),
                stage=str(JobStage.TRANSCRIBE),
                attempts=0,
                available_at=utcnow(),
            )
        )

    def claim(self, owner: str, *, lease_seconds: int) -> Job | None:
        """Take a lease on the next eligible job, or return None.

        Eligible means queued and due, or running with an expired lease. A job
        that was claimed but never released is therefore picked up again by
        whoever comes next.

        Taking the lease is a commitment to run the stage, so the caller records
        the Episode's status for that stage and commits both together: a status
        that says `transcribing` while the work is in flight is the observable
        part of asynchrony, and it must not be rolled back by whatever the stage
        does next.
        """
        now = utcnow()
        eligible = or_(
            (Job.state == str(JobState.QUEUED)) & (Job.available_at <= now),
            (Job.state == str(JobState.RUNNING)) & (Job.lease_expires_at <= now),
        )

        candidate = self.session.scalars(
            select(Job.job_id).where(eligible).order_by(Job.available_at).limit(1)
        ).one_or_none()
        if candidate is None:
            return None

        result = self.session.execute(
            update(Job)
            .where(Job.job_id == candidate, eligible)
            .values(
                state=str(JobState.RUNNING),
                lease_owner=owner,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                attempts=Job.attempts + 1,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            # Another worker claimed it first. This tick does nothing; the
            # Episode is not lost, the work is simply being done elsewhere.
            return None
        return self.get(candidate)

    def complete_stage(self, job: Job, owner: str, episode: Episode) -> bool:
        """Record a successful stage: advance the pipeline, or finish it.

        The job goes back to `queued` for the next stage rather than continuing
        in this tick, which is what makes each transition observable from outside
        the worker (Issue #1's definition of done). The Episode's status is not
        changed here: it already names the stage that just ran, and the next
        stage's status is committed when that stage is claimed — a status set
        ahead of the work would claim progress that has not happened.

        Returns False when the lease is no longer this worker's, in which case
        nothing was written and the caller must roll the transaction back: another
        worker owns this work now, and this stage's result is a duplicate of the
        one it is producing.
        """
        next_stage = NEXT_STAGE[JobStage(job.stage)]
        now = utcnow()
        values: dict[str, object] = {
            "lease_owner": None,
            "lease_expires_at": None,
            "updated_at": now,
        }
        awaiting_transcript_review = (
            JobStage(job.stage) is JobStage.TRANSCRIBE
            and episode.source in {"IOS_MIC", "IMPORT", "ANDROID_MIC"}
        )
        if awaiting_transcript_review:
            values.update(
                state=str(JobState.WAITING),
                stage=str(JobStage.EXTRACT),
                attempts=0,
            )
        elif next_stage is None:
            values["state"] = str(JobState.SUCCEEDED)
        else:
            values.update(
                state=str(JobState.QUEUED),
                stage=str(next_stage),
                available_at=now,
                # The retry budget is per stage: a stage that succeeded should not
                # spend the next stage's attempts.
                attempts=0,
            )

        if not self._release_if_held(job.job_id, owner, values):
            return False

        if next_stage is None:
            episode.status = str(EpisodeStatus.READY)
            episode.error_code = None
            episode.error_message = None
        return True

    def reschedule(
        self, job: Job, owner: str, episode: Episode, error: AppError, *, delay_seconds: int
    ) -> bool:
        """Put a failed stage back on the queue after a delay.

        The Episode keeps showing the stage it is stuck on and gains the error, so
        a client polling it can see that an attempt failed without being told the
        work is over. Returns False when the lease was lost, like `complete_stage`.
        """
        now = utcnow()
        if not self._release_if_held(
            job.job_id,
            owner,
            {
                "state": str(JobState.QUEUED),
                "available_at": now + timedelta(seconds=delay_seconds),
                "last_error_code": error.code,
                "updated_at": now,
            },
        ):
            return False

        episode.error_code = error.code
        episode.error_message = error.message
        return True

    def give_up(self, job: Job, owner: str, episode: Episode, error: AppError) -> bool:
        """Record a failure that will not be retried.

        The Episode keeps its row and its audio: a failed model does not get to
        destroy the original recording, so the Episode stays readable and its
        status explains what happened. Returns False when the lease was lost.
        """
        now = utcnow()
        if not self._release_if_held(
            job.job_id,
            owner,
            {
                "state": str(JobState.FAILED),
                "last_error_code": error.code,
                "updated_at": now,
            },
        ):
            return False

        episode.status = str(EpisodeStatus.FAILED)
        episode.error_code = error.code
        episode.error_message = error.message
        return True

    def renew_lease(self, job_id: str, owner: str, *, lease_seconds: int) -> bool:
        """Push this worker's lease out while a long stage runs.

        Renewal is what keeps a stage that outlives its lease from being executed
        twice in the first place. It is deliberately *not* what makes a double
        commit impossible — `_release_if_held` is — because a renewal can always
        be the one that did not happen: the process may be descheduled, the
        database briefly unreachable, or the lease already gone between two
        heartbeats. Returns False once the row is no longer this worker's, which
        the caller reads as "stop renewing and let the commit refuse".
        """
        now = utcnow()
        result = self.session.execute(
            self._still_ours(job_id, owner, now).values(
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )
        return result.rowcount == 1

    def _release_if_held(self, job_id: str, owner: str, values: dict[str, object]) -> bool:
        """The leased `UPDATE` every stage outcome goes through.

        The lease condition is part of the statement rather than a read that
        precedes it, so the database decides whether this worker still owns the
        work at the instant of the write. A matched row count of one is the whole
        answer: zero means the lease was not this worker's and nothing was
        written.

        `synchronize_session=False` because the caller holds the ORM row as its
        *input* — the row it just mutated is written by this statement instead,
        and letting the ORM also flush its own copy would write a second,
        unconditioned `UPDATE` over the same columns.
        """
        result = self.session.execute(
            self._still_ours(job_id, owner, utcnow()).values(**values)
        )
        return result.rowcount == 1

    def _still_ours(self, job_id: str, owner: str, now):  # type: ignore[no-untyped-def]
        """`UPDATE jobs` restricted to a job this worker holds an unexpired lease on."""
        return (
            update(Job)
            .where(
                Job.job_id == job_id,
                Job.lease_owner == owner,
                Job.lease_expires_at > now,
                Job.state == str(JobState.RUNNING),
            )
            .execution_options(synchronize_session=False)
        )
