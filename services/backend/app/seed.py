"""Local development seed.

Creates a Subject, an Actor holding a fresh token, and a granted RECORDING
consent, which is the record Issue #8's definition of done asks for: a persisted
record that references a Subject and an Actor, with consent recorded.

    uv run python -m app.seed --subject-name "Ada" --actor-name "Ada"
"""

import argparse
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from .config import get_settings
from .db import Database
from .models import Actor, Consent, ConsentScope, ConsentStatus, Subject, utcnow
from .tokens import generate_actor_token, hash_actor_token


@dataclass(frozen=True)
class SeedResult:
    subject_id: str
    actor_id: str
    consent_id: str
    actor_token: str


def seed_development_data(
    session: Session, *, subject_name: str, actor_name: str
) -> SeedResult:
    subject = Subject(
        subject_id=f"subj_{uuid4().hex[:16]}", display_name=subject_name
    )
    token = generate_actor_token()
    actor = Actor(
        actor_id=f"actor_{uuid4().hex[:16]}",
        display_name=actor_name,
        token_hash=hash_actor_token(token),
    )
    session.add_all([subject, actor])
    session.flush()

    consent = Consent(
        consent_id=f"consent_{uuid4().hex[:16]}",
        subject_id=subject.subject_id,
        granted_by_actor_id=actor.actor_id,
        scope=str(ConsentScope.RECORDING),
        status=str(ConsentStatus.GRANTED),
        granted_at=utcnow(),
        evidence_ref="local-development-seed",
    )
    session.add(consent)
    session.commit()

    return SeedResult(
        subject_id=subject.subject_id,
        actor_id=actor.actor_id,
        consent_id=consent.consent_id,
        actor_token=token,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local development data.")
    parser.add_argument("--subject-name", default="Local Subject")
    parser.add_argument("--actor-name", default="Local Actor")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_url)
    session = database.session()
    try:
        result = seed_development_data(
            session, subject_name=args.subject_name, actor_name=args.actor_name
        )
    finally:
        session.close()
        database.dispose()

    print(f"subject_id : {result.subject_id}")
    print(f"actor_id   : {result.actor_id}")
    print(f"consent_id : {result.consent_id}")
    print(f"actor token: {result.actor_token}")
    print()
    print("The token is local development material. It is not a production")
    print("credential and is not stored anywhere except as a digest.")


if __name__ == "__main__":
    main()