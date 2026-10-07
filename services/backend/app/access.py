"""Authorization is a data filter, never a prompt instruction."""
from sqlalchemy import select
from .errors import AppError
from .models import Subject, Episode, StoryGrant, Consent


class Hidden(AppError):
    code = 'NOT_FOUND'
    http_status = 404


def is_owner(session, subject_id, actor_id):
    subject = session.get(Subject, subject_id)
    return subject is not None and subject.owner_actor_id == actor_id


def require_owner(session, subject_id, actor_id):
    if not is_owner(session, subject_id, actor_id):
        raise Hidden('人物空间不存在或尚未映射所有者。')


def altered_story_ids(session, episode_ids):
    """Whole audio cannot be safely redacted; readers lose an altered source.

    Owners keep their original history. A fresh private revision does not grant
    a reader access to its replacement or resurrect the old reviewed wording.
    """
    from .models import MemoryItem, MemoryRevision
    from sqlalchemy import or_
    altered = set(session.scalars(select(MemoryItem.episode_id).where(
        MemoryItem.episode_id.in_(episode_ids), or_(MemoryItem.deleted_at.is_not(None),
            MemoryItem.review_state != 'active', MemoryItem.source_type == 'CALIBRATION'))))
    altered.update(session.scalars(select(MemoryRevision.episode_id).where(
        MemoryRevision.episode_id.in_(episode_ids), MemoryRevision.status != 'confirmed')))
    return altered


def visible_episodes(session, subject_id, actor_id, *, cloud=False):
    if is_owner(session, subject_id, actor_id):
        return set(session.scalars(select(Episode.episode_id).where(Episode.subject_id == subject_id)))
    subject = session.get(Subject, subject_id)
    if subject is None or subject.owner_actor_id is None:
        raise Hidden('人物空间不可用。')
    query = select(StoryGrant.episode_id).join(Episode).where(
        Episode.subject_id == subject_id, StoryGrant.reader_actor_id == actor_id,
        StoryGrant.revoked_at.is_(None), Episode.status == 'ready')
    if cloud:
        query = query.where(StoryGrant.cloud_processing_allowed == 1)
    ids = set(session.scalars(query))
    if not ids:
        raise Hidden('没有可访问的故事。')
    return ids


def require_cloud(session, subject_id, actor_id, consent_id):
    from .repositories.consents import ConsentRepository
    from .models import ConsentScope
    if is_owner(session, subject_id, actor_id):
        ConsentRepository(session).require_active(consent_id, subject_id=subject_id,
            actor_id=actor_id, scope=ConsentScope.CLOUD_TWIN)
    else:
        ids = visible_episodes(session, subject_id, actor_id, cloud=True)
        grant = session.get(StoryGrant, consent_id)
        if (grant is None or grant.reader_actor_id != actor_id or grant.revoked_at is not None
                or not grant.cloud_processing_allowed or grant.episode_id not in ids):
            raise Hidden('请明确同意使用已获云端处理授权的故事进行问答。')


def source_basis(session, subject_id, *, include_profiles=True):
    """Hash ALL potentially used source and authorization state, not only citations.

    Caller uses a short snapshot/publication transaction. No provider calls here.
    """
    import hashlib
    import json
    from .models import MemoryItem, Evidence, PersonTrait, GraphFact, ModelRevision, MemoryRevision, ProfileCandidate
    parts = []
    queries = [select(Subject).where(Subject.subject_id == subject_id),
        select(Episode).where(Episode.subject_id == subject_id),
        select(MemoryItem).join(Episode).where(Episode.subject_id == subject_id),
        select(Evidence).join(Episode).where(Episode.subject_id == subject_id),
        select(PersonTrait).where(PersonTrait.subject_id == subject_id),
        select(GraphFact).where(GraphFact.subject_id == subject_id),
        select(ModelRevision).where(ModelRevision.subject_id == subject_id),
        select(Consent).where(Consent.subject_id == subject_id),
        select(StoryGrant).join(Episode).where(Episode.subject_id == subject_id),
        select(MemoryRevision).where(MemoryRevision.subject_id == subject_id)]
    if include_profiles:
        queries.append(select(ProfileCandidate).where(ProfileCandidate.subject_id == subject_id))
    for query in queries:
        rows = [{column.name: getattr(row, column.name) for column in row.__table__.columns}
                for row in session.scalars(query.execution_options(populate_existing=True))]
        parts.append(sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str)))
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


def publication_lock(session, subject_id):
    """Start fresh; serialize the short final compare+publish with source writes.

    SQLite's writer lock covers all mutators, including workers. On PostgreSQL
    use SERIALIZABLE and let conflicts abort, rather than claim a row lock stops
    arbitrary inserts. PostgreSQL acceptance is tracked separately.
    """
    from sqlalchemy import text
    session.rollback()
    session.expire_all()
    if session.bind.dialect.name == 'sqlite':
        session.execute(text('BEGIN IMMEDIATE'))
    else:
        session.connection(execution_options={'isolation_level': 'SERIALIZABLE'})
