#!/usr/bin/env python3
"""Run a reproducible HTTP loop or serve the Android shell. No production claim."""

from __future__ import annotations
import argparse
from contextlib import ExitStack
from io import BytesIO
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave
from fastapi import Request
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "services/backend"
AI = ROOT / "services/ai-core"
sys.path.insert(0, str(BACKEND))


def fixture_stt(port):
    from fastapi import FastAPI
    import uvicorn

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "fixture"}

    @app.post("/transcribe")
    async def transcribe(request: Request):
        audio = await request.body()
        if len(audio) > 25 * 1024 * 1024:
            from fastapi.responses import JSONResponse

            return JSONResponse({"error": "too large"}, status_code=413)
        # Explicit offline simulator. This never decodes or recognizes speech.
        text = (
            "周末我喜欢和家人一起吃饭。"
            if audio.endswith(b"fixture-second")
            else "工作日下班后我喜欢一个人待着。"
        )
        return {"text": text, "model_version": "fixture-stt-agent-demo-v1"}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def launch(stack, command, cwd, env, log_path):
    log = stack.enter_context(log_path.open("a"))
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log)

    def stop():
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    stack.callback(stop)
    return process


def check_ports(ports):
    with ExitStack() as stack:
        for port in ports:
            listener = stack.enter_context(socket.socket())
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise RuntimeError(
                    f"Port {port} is unavailable. A demo may already be running; "
                    "open its browser console or stop it with Ctrl-C before restarting."
                ) from error


def check_processes(processes, log_dir):
    for name, process in processes.items():
        code = process.poll()
        if code is not None:
            raise RuntimeError(f"{name} exited with code {code}; read {log_dir / (name + '.log')}")


def wait_health(url, process):
    import httpx

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Service exited; read the demo log")
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Service health timeout; read the demo log")


def wave_bytes(second=False):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 16000)
    return buffer.getvalue() + (b"fixture-second" if second else b"fixture-first")


def exercise(settings, session_data, base_url, output):
    import httpx
    from app.db import Database
    from app.worker import build_worker

    headers = {"Authorization": "Bearer " + session_data["actor_token"]}
    prefix = "/experimental/agent/v1/subjects/" + session_data["subject_id"]
    database = Database(settings.database_url)
    worker = build_worker(database, settings)
    with httpx.Client(base_url=base_url, headers=headers, timeout=120) as client:

        def call(path, body=None, method="POST"):
            response = client.request(method, prefix + path, json=body)
            response.raise_for_status()
            return response.json()

        call(
            "/grant",
            dict(
                recording_consent_id=session_data["recording_consent_id"],
                cloud_twin_consent=True,
                subject_single_speaker=True,
            ),
        )

        def ingest(second=False):
            response = client.post(
                "/api/v1/episodes",
                data=dict(
                    subject_id=session_data["subject_id"],
                    recording_consent_id=session_data["recording_consent_id"],
                    audio_ref="fixture-silence.wav",
                    idempotency_key="fixture-" + str(time.time_ns()),
                    source="IMPORT",
                    recorded_at="2026-10-03T00:00:00Z",
                    metadata=json.dumps(
                        {"agent_subject_single_speaker": True, "fixture_audio": True}
                    ),
                ),
                files={
                    "file": ("fixture-silence.wav", wave_bytes(second), "audio/wav")
                },
            )
            response.raise_for_status()
            eid = response.json()["episode_id"]
            for _ in range(3):
                if worker.run_once() != eid:
                    raise RuntimeError(
                        "Worker did not complete stage; inspect status/log"
                    )
            result = client.get(f"/api/v1/episodes/{eid}/result")
            result.raise_for_status()
            return eid, result.json()

        eid, result = ingest()
        model = call("/model", method="GET")
        question = "工作日下班后喜欢怎么度过？"
        twin = call("/twin", {"question": question})
        locked = call("/calibrations", {"question": question})
        completed = call(
            f"/calibrations/{locked['calibration_id']}/submit",
            {
                "human_answer": "我现在喜欢先和家人聊聊天，再自己待一会儿。",
                "expected_revision": model["revision"],
            },
        )
        corrected_model = call("/model", method="GET")
        plan = call("/plan", method="GET")
        next_eid, _ = ingest(second=True)
        after = call("/model", method="GET")
        assert completed["locked_answer"] == locked["locked_answer"]
        assert completed["lock_digest"] == locked["lock_digest"]
        assert len(completed["comparison"]["dimension_diffs"]) == 5
        assert after["revision"] == model["revision"] + 2
        summary = dict(
            mode="OFFLINE_FIXTURE",
            warning="Speech and semantic quality are not verified; WAV is silence.",
            first_episode_id=eid,
            memory_count=len(result["memory_items"]),
            initial_revision=model["revision"],
            initial_model=model,
            corrected_model=corrected_model,
            twin=twin,
            locked_calibration=locked,
            completed_calibration=completed,
            plan=plan,
            next_episode_id=next_eid,
            final_model=after,
        )
        output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(
            f"Loop verified: Memory {summary['memory_count']} → revision {model['revision']} → {twin['response_type']} → LOCKED → five dimensions → revision {completed['resulting_revision']} → next Capture → revision {after['revision']}"
        )
        print(f"Reviewable result: {output}")
    database.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Keep API, AI Core and worker running for Android",
    )
    parser.add_argument("--mode", choices=["fixture", "configured"],
                        help="--serve defaults to configured; one-shot defaults to fixture")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--ai-port", type=int, default=8100)
    parser.add_argument("--stt-port", type=int, default=8200)
    parser.add_argument("--internal-fixture-stt", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.internal_fixture_stt:
        return fixture_stt(args.internal_fixture_stt)
    if args.mode is None:
        args.mode = "configured" if args.serve else "fixture"
    from alembic import command
    from alembic.config import Config
    from app.config import Settings
    from app.db import Database
    from app.seed import seed_development_data

    if args.mode == "configured" and not args.serve:
        parser.error(
            "configured mode requires --serve; use real Android recording for provider acceptance"
        )
    ports = [args.backend_port, args.ai_port]
    if args.mode == "fixture":
        ports.append(args.stt_port)
    try:
        check_ports(ports)
    except RuntimeError as error:
        parser.error(str(error))
    state_dir = ROOT / "build/agent-demo" / args.mode
    state_dir.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        run_dir = (
            state_dir
            if args.serve
            else Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="remember-agent-demo-")
                )
            )
        )
        ai_env = os.environ.copy()
        ai_env.update(AI_AGENT_ENABLED="true")
        if args.mode == "fixture":
            print(
                "OFFLINE FIXTURE: STT ignores speech; schema workers are deterministic simulators.",
                flush=True,
            )
            ai_env.update(
                AI_PROVIDER="fixture",
                AI_MODEL="fixture-ai-v2",
                AI_MODEL_VERSION="fixture-ai-v2",
                AI_ENVIRONMENT="development",
                REMEMBER_ENVIRONMENT="development",
            )
            ai_env.pop("AI_API_KEY", None)
            settings = Settings(
                _env_file=None,
                environment="development",
                agent_enabled=True,
                ai_backend="http",
                ai_core_url=f"http://127.0.0.1:{args.ai_port}",
                stt_backend="http",
                stt_url=f"http://127.0.0.1:{args.stt_port}",
                database_url=f"sqlite:///{run_dir / 'remember.db'}",
                object_store_root=str(run_dir / "audio"),
            )
        else:
            settings = Settings(
                _env_file=BACKEND / ".env",
                agent_enabled=True,
                ai_backend="http",
                ai_core_url=f"http://127.0.0.1:{args.ai_port}",
                database_url=f"sqlite:///{run_dir / 'remember.db'}",
                object_store_root=str(run_dir / "audio"),
            )
            if settings.stt_backend not in {"http", "dashscope"}:
                parser.error(
                    "configure REMEMBER_STT_BACKEND=http or dashscope in services/backend/.env"
                )
            # AI Core reads its own .env. Explicitly refuse fixture in configured mode.
            ai_env["AI_ENVIRONMENT"] = "staging"
            ai_env["REMEMBER_ENVIRONMENT"] = "staging"
        migration = Config(str(BACKEND / "alembic.ini"))
        migration.set_main_option("script_location", str(BACKEND / "migrations"))
        migration.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(migration, "head")
        database = Database(settings.database_url)
        credential_file = run_dir / "session.json"
        if credential_file.exists():
            session_data = json.loads(credential_file.read_text())
        else:
            with database.session() as db_session:
                seed = seed_development_data(
                    db_session,
                    subject_name="Agent 演示本人",
                    actor_name="Agent 演示本人",
                )
                session_data = dict(
                    subject_id=seed.subject_id,
                    actor_token=seed.actor_token,
                    recording_consent_id=seed.consent_id,
                )
            credential_file.write_text(
                json.dumps(session_data, ensure_ascii=False, indent=2) + "\n"
            )
            credential_file.chmod(0o600)
        database.dispose()
        backend_env = os.environ.copy()
        backend_env.update(
            {
                "REMEMBER_" + k.upper(): v.get_secret_value() if isinstance(v, SecretStr) else str(v)
                for k, v in settings.model_dump().items()
                if v is not None
            }
        )
        backend_url = f"http://127.0.0.1:{args.backend_port}"
        backend_env.update(REMEMBER_DEMO_SESSION_FILE=str(credential_file), REMEMBER_DEMO_MODE=args.mode)
        if args.mode == "fixture":
            stt = launch(
                stack,
                [
                    str(BACKEND / ".venv/bin/python"),
                    str(Path(__file__).resolve()),
                    "--internal-fixture-stt",
                    str(args.stt_port),
                ],
                ROOT,
                backend_env,
                state_dir / "stt.log",
            )
            wait_health(f"http://127.0.0.1:{args.stt_port}", stt)
        ai = launch(
            stack,
            [
                str(AI / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.ai_port),
            ],
            AI,
            ai_env,
            state_dir / "ai.log",
        )
        wait_health(settings.ai_core_url, ai)
        backend = launch(
            stack,
            [
                str(BACKEND / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "agent_console.server:create_app",
                "--factory",
                "--app-dir",
                str(ROOT / "scripts"),
                "--host",
                "127.0.0.1",
                "--port",
                str(args.backend_port),
            ],
            BACKEND,
            backend_env,
            state_dir / "backend.log",
        )
        wait_health(backend_url, backend)
        if args.serve:
            worker = launch(
                stack,
                [str(BACKEND / ".venv/bin/python"), "-m", "app.worker"],
                BACKEND,
                backend_env,
                state_dir / "worker.log",
            )
            processes = dict(backend=backend, ai=ai, worker=worker)
            if args.mode == "fixture":
                processes["stt"] = stt
            check_processes(processes, state_dir)
            print(
                f"Browser console: {backend_url}/debug/agent/\nAndroid Backend: {backend_url}\nLocal session values: {credential_file}\nCtrl-C stops the demo; the database remains for reconnect.",
                flush=True,
            )
            try:
                while True:
                    check_processes(processes, state_dir)
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            exercise(settings, session_data, backend_url, state_dir / "last-loop.json")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(f"Demo stopped: {error}", file=sys.stderr)
        sys.exit(1)
