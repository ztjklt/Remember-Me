"""Operator-selected fictional demo identities; regular ACLs still apply."""
from sqlalchemy import select
from .models import Actor, Subject
from .access import Hidden


def demo_identity(settings, actor_id):
    if not settings.demo_accounts_enabled:
        return {}
    role = ('owner' if actor_id == settings.demo_owner_actor_id else
            'relative' if actor_id == settings.demo_relative_actor_id else '')
    return {'demo_role': role, 'demo_subject_id': settings.demo_subject_id} if role else {}


def demo_actor(settings, session, role):
    if not settings.demo_accounts_enabled:
        raise Hidden('演示入口暂未开放。')
    owner, relative = settings.demo_owner_actor_id, settings.demo_relative_actor_id
    subject = session.get(Subject, settings.demo_subject_id) if settings.demo_subject_id else None
    # Fail closed on incomplete or accidentally swapped configuration. The owner
    # account must not own a second space which could be exposed by this entrance.
    owned = list(session.scalars(select(Subject.subject_id).where(Subject.owner_actor_id == owner)))
    if (not owner or not relative or owner == relative or not subject or
            subject.owner_actor_id != owner or owned != [subject.subject_id] or
            not session.get(Actor, owner) or not session.get(Actor, relative)):
        raise Hidden('演示身份尚未配置完成。')
    return session.get(Actor, owner if role == 'owner' else relative)
