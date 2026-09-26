"""Print a one-time code and certificate fingerprint for the paired iPhone."""

import argparse
import hashlib
import subprocess
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select

from .config import get_settings
from .db import Database
from .models import Actor, PairingCode, Subject, utcnow
from .tokens import generate_actor_token, hash_actor_token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actor-id", help="Defaults to the sole local Actor")
    parser.add_argument("--subject-id", help="Defaults to the sole local Subject")
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--url", required=True, help="HTTPS LAN URL with certificate SAN for its host")
    args = parser.parse_args()
    if not args.url.startswith("https://"):
        parser.error("--url must use HTTPS")
    der = subprocess.check_output(["openssl", "x509", "-in", str(args.cert), "-outform", "DER"])
    fingerprint = hashlib.sha256(der).hexdigest()
    code = generate_actor_token()
    db = Database(get_settings().database_url)
    with db.session() as session:
        actors = list(session.scalars(select(Actor.actor_id)))
        subjects = list(session.scalars(select(Subject.subject_id)))
        actor_id = args.actor_id or (actors[0] if len(actors) == 1 else None)
        subject_id = args.subject_id or (subjects[0] if len(subjects) == 1 else None)
        if not actor_id or not subject_id:
            parser.error("Provide --actor-id and --subject-id when the database has multiple people")
        session.add(PairingCode(code_hash=hash_actor_token(code), actor_id=actor_id,
                                subject_id=subject_id, expires_at=utcnow() + timedelta(minutes=10)))
        session.commit()
    db.dispose()
    print(f"Server: {args.url}")
    print(f"One-time code (10 minutes): {code}")
    print(f"Certificate SHA-256: {fingerprint}")
    print(f"Pairing link: rememberme://pair?server={args.url}&code={code}&sha256={fingerprint}")


if __name__ == "__main__":
    main()
