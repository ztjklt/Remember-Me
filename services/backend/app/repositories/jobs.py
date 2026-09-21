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

    def complete_stage(self, job: Job, episode: Episode) -> None:
        """Record a successful stage: advance the pipeline, or finish it.

        The job goes back to `queued` for the next stage rather than continuing
        in this tick, which is what makes each transition observable from outside
        the worker (Issue #1's definition of done). The Episode's status is not
        changed here: it already names the stage that just ran, and the next
        stage's status is committed when that stage is claimed — a status set
        ahead of the work would claim progress that has not happened.
        """
        next_stage = NEXT_STAGE[JobStage(job.stage)]
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = utcnow()

        if next_stage is None:
            job.state = str(JobState.SUCCEEDED)
            episode.status = str(EpisodeStatus.READY)
            episode.error_code = None
            episode.error_message = None
        else:
            job.state = str(JobState.QUEUED)
            job.stage = str(next_stage)
            job.available_at = utcnow()
            # The retry budget is per stage: a stage that succeeded should not
            # spend the next stage's attempts.
            job.attempts = 0

    def reschedule(self, job: Job, episode: Episode, error: AppError, *, delay_seconds: int) -> None:
        """Put a failed stage back on the queue after a delay.

        The Episode keeps showing the stage it is stuck on and gains the error, so
        a client polling it can see that an attempt failed without being told the
        work is over.
        """
        now = utcnow()
        job.state = str(JobState.QUEUED)
        job.lease_owner = None
        job.lease_expires_at = None
        job.available_at = now + timedelta(seconds=delay_seconds)
        job.last_error_code = error.code
        job.updated_at = now
        episode.error_code = error.code
        episode.error_message = error.message

    def give_up(self, job: Job, episode: Episode, error: AppError) -> None:
        """Record a failure that will not be retried.

        The Episode keeps its row and its audio: a failed model does not get to
        destroy the original recording, so the Episode stays readable and its
        status explains what happened.
        """
        now = utcnow()
        job.state = str(JobState.FAILED)
        job.lease_owner = None
        job.lease_expires_at = None
        job.last_error_code = error.code
        job.updated_at = now
        episode.status = str(EpisodeStatus.FAILED)
        episode.error_code = error.code
        episode.error_message = error.message