"""Minimum Phase 1 auth boundary.

An actor token resolves to an Actor, so work can be attributed to whoever
operated the app. This is deliberately not production authentication: there is
no identity provider, no rotation, and no expiry (Issue #8 non-goals). The Actor
record is the seam a real identity provider plugs into later.
"""

from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .errors import AuthInvalid, AuthRequired
from .models import Account, Actor, LoginSession
from .repositories.actors import ActorRepository
from .tokens import hash_actor_token

_BEARER_PREFIX = "Bearer "


def current_actor(request: Request, session: Session = Depends(get_session)) -> Actor:
    """Resolve the caller's actor token, or fail with a stable error code."""
    header = request.headers.get("Authorization")
    if header is None or not header.startswith(_BEARER_PREFIX):
        raise AuthRequired("An 'Authorization: Bearer <actor token>' header is required")

    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise AuthRequired("The bearer credential was empty")

    active = session.scalar(select(LoginSession).where(LoginSession.access_hash == hash_actor_token(token)))
    if active is not None:
        now = datetime.now(timezone.utc)
        expiry = active.access_expires_at.replace(tzinfo=timezone.utc) if active.access_expires_at.tzinfo is None else active.access_expires_at
        if active.revoked_at is not None or expiry <= now:
            raise AuthInvalid("The session expired")
        actor = session.get(Actor, active.actor_id)
    else:
        actor = ActorRepository(session).find_by_token(token)
        if actor is not None and session.scalar(select(Account.email).where(Account.actor_id == actor.actor_id)):
            actor = None
        if actor is not None and request.app.state.settings.environment not in {"development", "test"}:
            actor = None
    if actor is None:
        raise AuthInvalid("The actor token is not recognized")
    return actor


def require_subject_owner(session: Session, *, subject_id: str, actor_id: str) -> None:
    """A claimed Subject cannot be self-authorized by another Actor."""
    from .errors import SubjectNotFound

    owner = session.scalar(select(Account).where(Account.subject_id == subject_id))
    if owner is not None and owner.actor_id != actor_id:
        raise SubjectNotFound("No accessible Subject")
    own_account = session.scalar(select(Account).where(Account.actor_id == actor_id))
    if own_account is not None and own_account.subject_id != subject_id:
        raise SubjectNotFound("No accessible Subject")
