"""Run the isolated iOS branch's Backend path with real local STT and AI.

Prerequisites: the STT bridge on :8200 and AI Core on :8100 must already use
real providers. PHASE1_AUDIO_PATH points to a consented audio file. This script
creates a temporary database/Actor/Subject, starts Backend and worker, verifies
the persisted Episode, then stops them. It does not satisfy device acceptance.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "services" / "backend"
VERIFY = ROOT / "scripts" / "verify_phase1_live.py"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def await_health(url: str, process: subprocess.Popen, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Backend exited before becoming ready")
        try:
            if httpx.get(url + "/health", timeout=1).is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError("Backend did not become ready")


def run() -> None:
    audio = Path(os.environ["PHASE1_AUDIO_PATH"]).expanduser().resolve()
    if not audio.is_file():
        raise ValueError("PHASE1_AUDIO_PATH must be a local audio file")
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="remember-me-ios-stack-") as temp:
        root = Path(temp)
        database_url = f"sqlite:///{root / 'remember.db'}"
        env = os.environ.copy()
        env.update({
            "REMEMBER_DATABASE_URL": database_url,
            "REMEMBER_OBJECT_STORE_BACKEND": "local",
            "REMEMBER_OBJECT_STORE_ROOT": str(root / "objects"),
            "REMEMBER_STT_BACKEND": "http",
            "REMEMBER_STT_URL": "http://127.0.0.1:8200",
            "REMEMBER_STT_TIMEOUT_SECONDS": "120",
            "REMEMBER_AI_BACKEND": "http",
            "REMEMBER_AI_CORE_URL": "http://127.0.0.1:8100",
            "REMEMBER_AI_TIMEOUT_SECONDS": "140",
        })
        subprocess.run(
            ["uv", "run", "--locked", "alembic", "upgrade", "head"],
            cwd=BACKEND, env=env, check=True, stdout=subprocess.DEVNULL,
        )

        # Seed in-process so the short-lived token never appears in command
        # arguments, terminal output or a plaintext file.
        os.environ.update({key: value for key, value in env.items() if key.startswith("REMEMBER_")})
        sys.path.insert(0, str(BACKEND))
        from app.db import Database
        from app.seed import seed_development_data

        db = Database(database_url)
        with db.session() as session:
            seed = seed_development_data(
                session, subject_name="Local iOS Verification",
                actor_name="Local iOS Verification",
            )
        db.dispose()

        verify_env = env.copy()
        verify_env.update({
            "PHASE1_BACKEND_URL": f"http://127.0.0.1:{port}",
            "PHASE1_ACTOR_TOKEN": seed.actor_token,
            "PHASE1_SUBJECT_ID": seed.subject_id,
            "PHASE1_RECORDING_CONSENT_ID": seed.consent_id,
            "PHASE1_AUDIO_PATH": str(audio),
            "PHASE1_RECORDED_AT": datetime.fromtimestamp(
                audio.stat().st_mtime, tz=timezone.utc
            ).isoformat(),
            "PHASE1_DATABASE_URL": database_url,
            "PHASE1_CAPTURE_SOURCE": "IMPORT",
            "PHASE1_TIMEOUT_SECONDS": "300",
        })
        with (root / "backend.log").open("w") as backend_log, (
            root / "worker.log"
        ).open("w") as worker_log:
            api = subprocess.Popen(
                ["uv", "run", "--locked", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=BACKEND, env=env, stdout=backend_log, stderr=subprocess.STDOUT,
            )
            worker = None
            try:
                await_health(verify_env["PHASE1_BACKEND_URL"], api)
                worker = subprocess.Popen(
                    ["uv", "run", "--locked", "python", "-m", "app.worker"],
                    cwd=BACKEND, env=env, stdout=worker_log,
                    stderr=subprocess.STDOUT,
                )
                subprocess.run(
                    ["uv", "run", "--locked", "python", str(VERIFY)],
                    cwd=BACKEND, env=verify_env, check=True,
                )
            finally:
                for process in (worker, api):
                    if process is not None:
                        process.terminate()
                for process in (worker, api):
                    if process is not None:
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()


if __name__ == "__main__":
    run()
