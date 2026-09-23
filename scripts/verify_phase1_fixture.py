"""Exercise the Phase 1 Backend -> AI Core HTTP path with disposable local data.

Run from the repository root after installing uv:

    cd services/backend && uv run --locked python ../../scripts/verify_phase1_fixture.py

This proves wiring with fake STT and AI Core's fixture provider. It cannot close
the real-device, real-provider Phase 1 gate.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "services/backend"
AI_CORE = ROOT / "services/ai-core"


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def command(cwd: Path, env: dict[str, str], *args: str) -> str:
    completed = subprocess.run(
        ["uv", "run", "--locked", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def seed_field(output: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\s*:\s*(\S+)", output, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"Local seed did not return {name}")
    return match.group(1)


def wait_for_health(client: httpx.Client, url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service at {url} exited before it became healthy")
        try:
            client.get(url + "/health").raise_for_status()
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f"Service at {url} did not become healthy")


def main() -> None:
    processes: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory(prefix="remember-phase1-fixture-") as temp:
        working = Path(temp)
        ai_port, backend_port = unused_port(), unused_port()
        ai_url = f"http://127.0.0.1:{ai_port}"
        backend_url = f"http://127.0.0.1:{backend_port}"

        backend_env = os.environ.copy()
        backend_env.update(
            REMEMBER_ENVIRONMENT="development",
            REMEMBER_DATABASE_URL=f"sqlite:///{working / 'remember.db'}",
            REMEMBER_OBJECT_STORE_BACKEND="local",
            REMEMBER_OBJECT_STORE_ROOT=str(working / "objects"),
            REMEMBER_STT_BACKEND="fake",
            REMEMBER_AI_BACKEND="http",
            REMEMBER_AI_CORE_URL=ai_url,
            REMEMBER_JOB_RETRY_BACKOFF_SECONDS="0",
        )
        ai_env = os.environ.copy()
        ai_env.update(REMEMBER_ENVIRONMENT="development", AI_PROVIDER="fixture")

        try:
            command(BACKEND, backend_env, "alembic", "upgrade", "head")
            seed = command(
                BACKEND, backend_env, "python", "-m", "app.seed",
                "--subject-name", "Fixture Subject", "--actor-name", "Fixture Actor",
            )
            subject = seed_field(seed, "subject_id")
            consent = seed_field(seed, "consent_id")
            token = seed_field(seed, "actor token")

            with (working / "ai.log").open("w") as ai_log, (
                working / "backend.log"
            ).open("w") as backend_log, (working / "worker.log").open("w") as worker_log:
                processes.append(
                    subprocess.Popen(
                        ["uv", "run", "--locked", "uvicorn", "app.main:app", "--host",
                         "127.0.0.1", "--port", str(ai_port)],
                        cwd=AI_CORE, env=ai_env, stdout=ai_log, stderr=subprocess.STDOUT,
                    )
                )
                processes.append(
                    subprocess.Popen(
                        ["uv", "run", "--locked", "uvicorn", "app.main:app", "--host",
                         "127.0.0.1", "--port", str(backend_port)],
                        cwd=BACKEND, env=backend_env, stdout=backend_log,
                        stderr=subprocess.STDOUT,
                    )
                )

                with httpx.Client(timeout=5) as client:
                    wait_for_health(client, ai_url, processes[0])
                    wait_for_health(client, backend_url, processes[1])
                    headers = {"Authorization": f"Bearer {token}"}
                    capture = {
                        "subject_id": subject,
                        "recording_consent_id": consent,
                        "source": "ANDROID_MIC",
                        "recorded_at": "2026-09-21T09:30:00+00:00",
                        "audio_ref": "fixture.m4a",
                        "idempotency_key": "phase1-fixture-001",
                    }
                    audio = b"RIFF\x00\x00\x00\x00WAVEfmt fixture bytes"

                    def upload() -> httpx.Response:
                        return client.post(
                            backend_url + "/api/v1/episodes",
                            headers=headers,
                            data=capture,
                            files={"file": ("fixture.m4a", audio, "audio/mp4")},
                        )

                    created = upload()
                    created.raise_for_status()
                    assert created.status_code == 201, created.status_code
                    episode_id = created.json()["episode_id"]

                    duplicate = upload()
                    duplicate.raise_for_status()
                    assert duplicate.status_code == 200
                    assert duplicate.json()["episode_id"] == episode_id

                    processes.append(
                        subprocess.Popen(
                            ["uv", "run", "--locked", "python", "-m", "app.worker"],
                            cwd=BACKEND, env=backend_env, stdout=worker_log,
                            stderr=subprocess.STDOUT,
                        )
                    )
                    deadline = time.monotonic() + 20
                    while True:
                        status_response = client.get(
                            backend_url + f"/api/v1/episodes/{episode_id}",
                            headers=headers,
                        )
                        status_response.raise_for_status()
                        status = status_response.json()
                        if status["status"] in {"ready", "failed"}:
                            break
                        if time.monotonic() > deadline:
                            raise RuntimeError(f"Episode stopped progressing at {status['status']}")
                        time.sleep(0.2)

                    result = client.get(
                        backend_url + f"/api/v1/episodes/{episode_id}/result",
                        headers=headers,
                    )
                    print(
                        "upload=201 duplicate=200"
                        f" episode={status['status']} result={result.status_code}"
                        f" error={status.get('error_code') or 'none'}"
                    )
                    if status["status"] != "ready" or result.status_code != 200:
                        raise RuntimeError("Fixture Golden Path did not reach a readable Memory")
                    body = result.json()
                    assert body["episode_id"] == episode_id
                    assert body["model_version"].startswith("fixture-ai-")
                    assert len(body["memory_items"]) >= 1
                    print(
                        f"model={body['model_version']}"
                        f" memories={len(body['memory_items'])}"
                        " (fixture wiring only)"
                    )
        finally:
            for process in reversed(processes):
                process.terminate()
            for process in reversed(processes):
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == "__main__":
    main()
