"""One-time HTTPS pairing for the local iPhone client."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import RequestInvalid
from ..models import Consent, DeviceCredential, PairingCode, utcnow
from ..tokens import generate_actor_token, hash_actor_token

router = APIRouter(prefix="/api/v1/local-pairing", tags=["local-pairing"])


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=20, max_length=128)


@router.post("/claim")
def claim(body: Claim, request: Request, session: Session = Depends(get_session)) -> dict:
    if request.url.scheme != "https":
        raise RequestInvalid("Pairing requires HTTPS")
    digest = hash_actor_token(body.code)
    code = session.get(PairingCode, digest)
    if code is None:
        raise RequestInvalid("Pairing code is invalid or expired")
    consent = session.query(Consent).filter_by(
        subject_id=code.subject_id, granted_by_actor_id=code.actor_id,
        scope="RECORDING", status="granted",
    ).first()
    if consent is None:
        raise RequestInvalid("Recording consent is required before pairing")
    changed = session.execute(update(PairingCode).where(
        PairingCode.code_hash == digest, PairingCode.used_at.is_(None),
        PairingCode.expires_at > utcnow(),
    ).values(used_at=utcnow()).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        session.rollback()
        raise RequestInvalid("Pairing code is invalid or expired")
    token = generate_actor_token()
    session.add(DeviceCredential(token_hash=hash_actor_token(token), actor_id=code.actor_id))
    session.commit()
    return {"actor_token": token, "actor_id": code.actor_id,
            "subject_id": code.subject_id, "recording_consent_id": consent.consent_id}
