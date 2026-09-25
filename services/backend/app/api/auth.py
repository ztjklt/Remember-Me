"""Email-code identity for a personal Actor and Subject."""

import hmac
import re
import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AuthInvalid, RequestInvalid
from ..models import (
    Account, AccountClaim, Actor, Consent, EmailChallenge, Episode,
    LoginSession, Subject, as_utc, utcnow,
)
from ..repositories.actors import ActorRepository
from ..security import current_actor
from ..tokens import generate_actor_token, hash_actor_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CODE_TTL = timedelta(minutes=10)
ACCESS_TTL = timedelta(minutes=20)
REFRESH_TTL = timedelta(days=30)


def _email(value: str) -> str:
    result = value.strip().lower()
    if not EMAIL_RE.fullmatch(result) or len(result) > 320:
        raise RequestInvalid("Enter a valid email address")
    return result


def _challenge_hash(email: str, code: str, secret: str) -> str:
    return hash_actor_token(f"{email}:{code}:{secret}")


def _tokens(session: Session, actor_id: str) -> tuple[str, str]:
    now = utcnow()
    access = generate_actor_token()
    refresh = generate_actor_token()
    session.add(LoginSession(
        session_id=f"login_{uuid4().hex}", actor_id=actor_id,
        access_hash=hash_actor_token(access), refresh_hash=hash_actor_token(refresh),
        access_expires_at=now + ACCESS_TTL, refresh_expires_at=now + REFRESH_TTL,
        created_at=now,
    ))
    return access, refresh


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)


class VerifyRequest(StartRequest):
    code: str = Field(pattern=r"^\d{6}$")


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(min_length=20)


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legacy_token: str = Field(min_length=20)
    subject_id: str = Field(min_length=1)


class AuthResult(BaseModel):
    access_token: str
    refresh_token: str
    actor_id: str
    subject_id: str
    email: str


def _result(account: Account, access: str, refresh: str) -> AuthResult:
    return AuthResult(
        access_token=access, refresh_token=refresh,
        actor_id=account.actor_id, subject_id=account.subject_id, email=account.email,
    )


@router.post("/email/start")
def start_email(payload: StartRequest, request: Request, session: Session = Depends(get_session)) -> dict[str, str]:
    email = _email(payload.email)
    now = utcnow()
    previous = session.get(EmailChallenge, email)
    if previous is not None and now - as_utc(previous.last_sent_at) < timedelta(seconds=60):
        raise RequestInvalid("Please wait before requesting another code")
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_urlsafe(16)
    challenge = previous or EmailChallenge(email=email)
    challenge.code_hash = f"{salt}:{_challenge_hash(email, code, salt)}"
    challenge.expires_at = now + CODE_TTL
    challenge.last_sent_at = now
    challenge.attempts = 0
    request.app.state.mailer.send_code(email, code)
    session.add(challenge)
    session.commit()
    return {"status": "sent"}


@router.post("/email/verify", response_model=AuthResult)
def verify_email(payload: VerifyRequest, session: Session = Depends(get_session)) -> AuthResult:
    email = _email(payload.email)
    challenge = session.get(EmailChallenge, email)
    now = utcnow()
    if challenge is None or now >= as_utc(challenge.expires_at) or challenge.attempts >= 5:
        raise AuthInvalid("Code expired or invalid")
    salt, digest = challenge.code_hash.split(":", 1)
    if not hmac.compare_digest(digest, _challenge_hash(email, payload.code, salt)):
        session.execute(
            update(EmailChallenge)
            .where(
                EmailChallenge.email == email,
                EmailChallenge.code_hash == challenge.code_hash,
                EmailChallenge.expires_at > now,
                EmailChallenge.attempts < 5,
            )
            .values(attempts=EmailChallenge.attempts + 1)
            .execution_options(synchronize_session=False)
        )
        session.commit()
        raise AuthInvalid("Code expired or invalid")
    consumed = session.execute(
        delete(EmailChallenge)
        .where(
            EmailChallenge.email == email,
            EmailChallenge.code_hash == challenge.code_hash,
            EmailChallenge.expires_at > now,
            EmailChallenge.attempts < 5,
        )
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        session.rollback()
        raise AuthInvalid("Code expired or invalid")
    account = session.get(Account, email)
    if account is None:
        actor = Actor(
            actor_id=f"actor_{uuid4().hex[:16]}", display_name=email.split("@", 1)[0],
            token_hash=hash_actor_token(generate_actor_token()), created_at=utcnow(),
        )
        subject = Subject(
            subject_id=f"subj_{uuid4().hex[:16]}", display_name=actor.display_name,
            created_at=utcnow(),
        )
        session.add_all([actor, subject])
        session.flush()
        account = Account(email=email, actor_id=actor.actor_id, subject_id=subject.subject_id, created_at=utcnow())
        session.add(account)
    access, refresh = _tokens(session, account.actor_id)
    session.commit()
    return _result(account, access, refresh)


@router.post("/refresh", response_model=AuthResult)
def refresh_session(payload: RefreshRequest, session: Session = Depends(get_session)) -> AuthResult:
    current = session.scalar(select(LoginSession).where(
        LoginSession.refresh_hash == hash_actor_token(payload.refresh_token)
    ))
    now = utcnow()
    if current is None or current.revoked_at is not None or now >= as_utc(current.refresh_expires_at):
        raise AuthInvalid("Session expired")
    account = session.scalar(select(Account).where(Account.actor_id == current.actor_id))
    if account is None:
        raise AuthInvalid("Account not found")
    # Consume the refresh credential with one conditional write. Concurrent
    # requests must not each mint a new session from the same credential.
    consumed = session.execute(
        update(LoginSession)
        .where(
            LoginSession.session_id == current.session_id,
            LoginSession.revoked_at.is_(None),
            LoginSession.refresh_expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    if consumed.rowcount != 1:
        session.rollback()
        raise AuthInvalid("Session expired")
    access, refresh = _tokens(session, account.actor_id)
    session.commit()
    return _result(account, access, refresh)


@router.post("/logout")
def logout(actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict[str, str]:
    for item in session.scalars(select(LoginSession).where(
        LoginSession.actor_id == actor.actor_id, LoginSession.revoked_at.is_(None)
    )):
        item.revoked_at = utcnow()
    session.commit()
    return {"status": "signed_out"}


@router.post("/claim", response_model=AuthResult)
def claim_legacy(
    payload: ClaimRequest, request: Request,
    actor: Actor = Depends(current_actor), session: Session = Depends(get_session),
) -> AuthResult:
    """One-time local migration; the old Actor owns only this Subject's data."""
    if request.app.state.settings.environment not in {"development", "test"}:
        raise AuthInvalid("Legacy claim is available only in local development")
    account = session.scalar(select(Account).where(Account.actor_id == actor.actor_id))
    old = ActorRepository(session).find_by_token(payload.legacy_token)
    if account is None or old is None or old.actor_id == actor.actor_id:
        raise AuthInvalid("Legacy credential is invalid")
    if session.scalar(select(Account.email).where(Account.actor_id == old.actor_id)):
        raise AuthInvalid("Legacy data has already been claimed")
    old_episode_subjects = set(session.scalars(select(Episode.subject_id).where(Episode.actor_id == old.actor_id)).all())
    old_consent_subjects = set(session.scalars(select(Consent.subject_id).where(Consent.granted_by_actor_id == old.actor_id)).all())
    if not old_episode_subjects | old_consent_subjects or (old_episode_subjects | old_consent_subjects) != {payload.subject_id}:
        raise AuthInvalid("Legacy Actor does not exclusively own this Subject's records")
    if session.scalar(select(Account.email).where(Account.subject_id == payload.subject_id)):
        raise AuthInvalid("Subject has already been claimed")
    if session.scalar(select(Episode.episode_id).where(Episode.actor_id == actor.actor_id).limit(1)) or session.scalar(
        select(Consent.consent_id).where(Consent.granted_by_actor_id == actor.actor_id).limit(1)
    ):
        raise RequestInvalid("Claim before recording or granting consent in the new account")
    new_actor = session.get(Actor, actor.actor_id)
    new_subject = session.get(Subject, account.subject_id)
    session.execute(delete(LoginSession).where(LoginSession.actor_id == actor.actor_id))
    account.actor_id = old.actor_id
    account.subject_id = payload.subject_id
    old.token_hash = hash_actor_token(generate_actor_token())
    session.flush()
    session.delete(new_actor)
    session.delete(new_subject)
    session.add(AccountClaim(
        claim_id=f"claim_{uuid4().hex[:16]}", email=account.email,
        old_actor_id=old.actor_id, subject_id=payload.subject_id, claimed_at=utcnow(),
    ))
    access, refresh = _tokens(session, old.actor_id)
    session.commit()
    return _result(account, access, refresh)
