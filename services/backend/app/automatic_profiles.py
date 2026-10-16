"""Queue cumulative analysis only after the recording's memories commit.

The queue lives in the same transaction as MODEL completion. No client polling
or open screen is needed for this second stage to happen.
"""
from sqlalchemy import select
from .access import require_cloud, require_owner
from .models import ProfileRefresh, Subject, utcnow


def enqueue_automatic_profile(session, episode):
    intent = (episode.capture_metadata or {}).get('automatic_profile') or {}
    consent = intent.get('consent_id')
    if not consent:
        return
    # Revocation stops cumulative cloud work, without discarding saved memories.
    try:
        require_owner(session, episode.subject_id, episode.actor_id)
        require_cloud(session, episode.subject_id, episode.actor_id, consent)
    except Exception as exc:
        from .errors import AppError
        if not isinstance(exc, AppError):
            raise
        episode.capture_metadata = {**episode.capture_metadata,
            'automatic_profile': {**intent, 'status': 'authorization_required'}}
        return
    session.scalar(select(Subject).where(Subject.subject_id == episode.subject_id).with_for_update())
    existing_id = intent.get('job_id')
    if existing_id and session.get(ProfileRefresh, existing_id) is not None:
        return
    # A running job has already captured its source snapshot. Always leave a
    # successor for new material; a queued job will read the latest full corpus.
    queued = session.scalars(select(ProfileRefresh).where(
        ProfileRefresh.subject_id == episode.subject_id,
        ProfileRefresh.actor_id == episode.actor_id,
        ProfileRefresh.kind == 'candidates', ProfileRefresh.status == 'queued'
    ).order_by(ProfileRefresh.created_at)).all()
    row = next((r for r in queued if (r.request_payload or {}).get('automatic')), None)
    if row is None:
        row = ProfileRefresh(job_id='auto_' + episode.episode_id, subject_id=episode.subject_id,
            actor_id=episode.actor_id, consent_id=consent, kind='candidates', status='queued',
            request_payload={'automatic': True, 'episode_ids': []})
        session.add(row)
    payload = row.request_payload or {}
    row.request_payload = {**payload, 'episode_ids': list(dict.fromkeys(
        payload.get('episode_ids', []) + [episode.episode_id]))[-100:], 'retry_count': 0}
    row.consent_id = consent
    row.updated_at = utcnow()
    episode.capture_metadata = {**episode.capture_metadata,
        'automatic_profile': {**intent, 'job_id': row.job_id, 'status': 'queued'}}


def automatic_retry(job, error, *, interrupted=False):
    """At most two retries, only for interruption, transport or stale snapshots."""
    from .errors import AppError
    payload = job.request_payload or {}
    count = payload.get('retry_count', 0)
    retryable = interrupted or (not isinstance(error, (ValueError, AppError))) or 'SOURCE_CHANGED' in str(error)
    if payload.get('automatic') and count < 2 and retryable:
        job.request_payload = {**payload, 'retry_count': count + 1}
        job.status, job.error, job.updated_at = 'queued', None, utcnow()
        return True
    return False
