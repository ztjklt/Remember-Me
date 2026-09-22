"""Minimum Phase 1 auth boundary.

An actor token resolves to an Actor, so work can be attributed to whoever
operated the app. This is deliberately not production authentication: there is
no identity provider, no rotation, and no expiry (Issue #8 non-goals). The Actor
record is the seam a real identity provider plugs into later.
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import get_session
from .errors import AuthInvalid, AuthRequired
from .models import Actor
from .repositories.actors import ActorRepository

_BEARER_PREFIX = "Bearer "


def current_actor(request: Request, session: Session = Depends(get_session)) -> Actor:
    """Resolve the caller's actor token, or fail with a stable error code."""
    header = request.headers.get("Authorization")
    if header is None or not header.startswith(_BEARER_PREFIX):
        raise AuthRequired("An 'Authorization: Bearer <actor token>' header is required")

    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise AuthRequired("The bearer credential was empty")

    actor = ActorRepository(session).find_by_token(token)
    if actor is None:
        raise AuthInvalid("The actor token is not recognized")
    return actor