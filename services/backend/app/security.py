"""Shared Actor boundary for legacy bearer, expiring device login, and web cookie.

Password accounts issue revocable 30-day device credentials. Legacy prototype
tokens remain compatible; public identity recovery and MFA are separate work.
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
    cookie = request.cookies.get('remember_session', '')
    if not header and cookie:
        if request.method not in {'GET','HEAD','OPTIONS'}:
            if request.headers.get('origin') != str(request.base_url).rstrip('/'):
                raise AuthRequired('请从当前服务页面重新发起操作。')
        header = _BEARER_PREFIX + cookie
    if header is None or not header.startswith(_BEARER_PREFIX):
        raise AuthRequired("An 'Authorization: Bearer <actor token>' header is required")

    token = header[len(_BEARER_PREFIX) :].strip()
    if not token:
        raise AuthRequired("The bearer credential was empty")

    actor = ActorRepository(session).find_by_token(token)
    if actor is None:
        raise AuthInvalid("The actor token is not recognized")
    return actor
