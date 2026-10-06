"""Local demo maintenance; preview by default, append a revision with --apply."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/backend"))

from app.agent_client import AgentClient
from app.agent_service import AgentService
from app.config import Settings
from app.db import Database
from app.errors import AuthInvalid
from app.repositories.actors import ActorRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-id", required=True)
    parser.add_argument("--expected-revision", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    state_dir = ROOT / "build/agent-demo/configured"
    session_data = json.loads((state_dir / "session.json").read_text())
    db_file = state_dir / "remember.db"
    settings = Settings(_env_file=ROOT / "services/backend/.env")
    database = Database(f"sqlite:///{db_file}")
    output_dir = ROOT / "build/agent-demo/provider-check"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        with database.session() as session:
            actor = ActorRepository(session).find_by_token(session_data["actor_token"])
            if actor is None:
                raise AuthInvalid("Local actor credential is invalid")
            service = AgentService(session, AgentClient(settings.ai_core_url, settings.agent_timeout_seconds))
            state = service.require(session_data["subject_id"], actor.actor_id)
            before = service.snapshot(state)
            calibration = service.view(service.record(state, args.calibration_id))
            if args.apply:
                backup = output_dir / f"before-calibration-{stamp}.db"
                backup.touch(mode=0o600)
                with sqlite3.connect(db_file) as original, sqlite3.connect(backup) as copied:
                    original.backup(copied)
            after = service.reapply_calibration(state, args.calibration_id, args.expected_revision, apply=args.apply)
            unchanged = service.view(service.record(state, args.calibration_id)) == calibration
            report = {"applied": args.apply, "model_before": before.model_dump(mode="json"),
                "model_after": after.model_dump(mode="json"), "calibration_unchanged": unchanged}
            output = output_dir / f"reapply-calibration-{stamp}.json"
            output.touch(mode=0o600)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"{'Applied' if args.apply else 'Preview'}: revision {before.revision} → {after.revision}")
            print(f"Private report: {output}")
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
