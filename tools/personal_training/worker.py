"""Outbound owner-authorized personal-training worker; never accepts inbound calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from typing import Callable
from urllib import error, parse, request
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "backend"))
from app.personal_training import DatasetPlan, MLXLoRATrainer, TrainingPolicy, TrainingResult


class WorkerError(RuntimeError):
    """Only a safe code is exposed; HTTP bodies and credentials stay private."""


class TransportError(WorkerError):
    def __init__(self, code: str, *, http_status: int | None = None):
        super().__init__(code)
        self.http_status = http_status


class WorkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    origin: str
    secret: str = Field(min_length=32, max_length=4096, repr=False)
    worker_id: str = Field(min_length=1, max_length=128)
    local_model: Path
    python: Path
    artifact_root: Path
    base_model: str = Field(default="Qwen/Qwen3-0.6B-MLX-4bit", min_length=1, max_length=256)

    @field_validator("origin")
    @classmethod
    def secure_origin(cls, value):
        parts = parse.urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in ("", "/")):
            raise ValueError("WORKER_HTTPS_ORIGIN_REQUIRED")
        return value.rstrip("/")


def read_config(path: Path) -> WorkerConfig:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or info.st_size > 16384):
        raise WorkerError("WORKER_CONFIG_MUST_BE_PRIVATE_0600")
    return WorkerConfig.model_validate_json(path.read_bytes())


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransportError("WORKER_REDIRECT_REJECTED", http_status=code)


class HTTPTransport:
    def __init__(self, config: WorkerConfig):
        self.origin, self.secret = config.origin, config.secret
        # No redirect can forward the secret. No shell or proxy environment is used.
        self.opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def post(self, endpoint: str, body: dict) -> dict:
        if not endpoint.startswith("/internal/personal-learning/"):
            raise WorkerError("WORKER_ENDPOINT_NOT_ALLOWED")
        payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        req = request.Request(self.origin + endpoint, data=payload, method="POST", headers={
            "Content-Type": "application/json", "X-Personal-Trainer-Secret": self.secret})
        try:
            with self.opener.open(req, timeout=8) as response:
                if response.status != 200:
                    raise TransportError("WORKER_HTTP_FAILED", http_status=response.status)
                if int(response.headers.get("Content-Length", "0")) > 16 * 1024 * 1024:
                    raise TransportError("WORKER_RESPONSE_TOO_LARGE")
                raw = response.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise TransportError("WORKER_RESPONSE_TOO_LARGE")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise TransportError("WORKER_RESPONSE_INVALID")
                return value
        except error.HTTPError as exc:
            raise TransportError("WORKER_HTTP_FAILED", http_status=exc.code) from None
        except (error.URLError, TimeoutError, OSError, ValueError):
            raise TransportError("WORKER_TRANSPORT_FAILED") from None


class ClaimJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    lease_token: str = Field(min_length=1, max_length=4096, repr=False)
    base_model: str = Field(min_length=1, max_length=256)
    plan: DatasetPlan
    policy: TrainingPolicy


class ClaimResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job: ClaimJob | None
    # The transport caps the complete response size. A fixed item cap would
    # permanently stop cleanup after enough historical revocations accumulate.
    purge_job_ids: list[str] = Field(default_factory=list)


class PersonalTrainingWorker:
    def __init__(self, config: WorkerConfig, *, transport=None, trainer=None,
                 monotonic: Callable[[], float] = time.monotonic):
        self.config = config
        self.transport = transport or HTTPTransport(config)
        self.trainer = trainer or MLXLoRATrainer(python=config.python, model=config.local_model,
            worker=Path(__file__).with_name("mlx_job.py"), artifact_root=config.artifact_root)
        self.clock = monotonic
        self.root = config.artifact_root.absolute()
        if self.root.is_symlink():
            raise WorkerError("WORKER_ARTIFACT_ROOT_UNSAFE")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.state_path = self.root / ".personal-worker-state.json"
        if self.state_path.is_symlink():
            raise WorkerError("WORKER_STATE_UNSAFE")
        if self.state_path.exists():
            if stat.S_IMODE(self.state_path.stat().st_mode) != 0o600:
                raise WorkerError("WORKER_STATE_MUST_BE_PRIVATE")
            self.state = json.loads(self.state_path.read_text())
            if not isinstance(self.state, dict) or set(self.state) != {"worker_id", "artifacts", "pending"}:
                raise WorkerError("WORKER_STATE_INVALID")
            if self.state["worker_id"] != config.worker_id or not isinstance(self.state["artifacts"], dict):
                raise WorkerError("WORKER_STATE_OWNER_MISMATCH")
        else:
            self.state = {"worker_id": config.worker_id, "artifacts": {}, "pending": None}
            self._save()

    def _save(self):
        temp = self.state_path.with_name(self.state_path.name + "." + uuid4().hex + ".tmp")
        if temp.exists() or temp.is_symlink():
            raise WorkerError("WORKER_STATE_TEMP_UNSAFE")
        with temp.open("x", encoding="utf-8") as handle:
            os.chmod(temp, 0o600)
            handle.write(json.dumps(self.state, ensure_ascii=False, allow_nan=False))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.state_path)

    def _purge(self, job_id: str):
        relative = self.state["artifacts"].get(job_id)
        if relative is None:
            return
        # Delete only a trainer-produced direct child, never supplied server paths.
        if not isinstance(relative, str) or not re.fullmatch(r"[a-f0-9-]{20,80}", relative):
            raise WorkerError("WORKER_ARTIFACT_MAPPING_INVALID")
        path = self.root / relative
        if path.is_symlink():
            path.unlink()
        elif path.exists():
            if path.resolve().parent != self.root.resolve():
                raise WorkerError("WORKER_PURGE_OUTSIDE_ROOT")
            shutil.rmtree(path)
        self.state["artifacts"].pop(job_id)
        pending = self.state["pending"]
        if pending and pending["job_id"] == job_id:
            self.state["pending"] = None
        self._save()

    def _upload_pending(self) -> bool:
        pending = self.state["pending"]
        if not pending:
            return True
        job_id = pending["job_id"]
        try:
            response = self.transport.post(f"/internal/personal-learning/jobs/{job_id}/result", {
                "worker_id": self.config.worker_id, "lease_token": pending["lease_token"],
                "result": pending["result"]})
            if not isinstance(response.get("status"), str):
                raise TransportError("WORKER_RESULT_RESPONSE_INVALID")
            if response["status"] in {"revoked", "stale"}:
                self._purge(job_id)
        except TransportError as exc:
            if exc.http_status in {401, 403, 404, 409}:
                self._purge(job_id)
                self.state["pending"] = None
                self._save()
                return True
            return False
        self.state["pending"] = None
        self._save()
        return True

    def tick(self) -> str:
        """Claim at most one job. Safe status only; never return source text."""
        if not self._upload_pending():
            return "result_waiting_for_server"
        claim = ClaimResponse.model_validate(self.transport.post("/internal/personal-learning/claim", {
            "worker_id": self.config.worker_id, "base_model": self.config.base_model,
            "available": self.trainer.capability().available}))
        for job_id in claim.purge_job_ids:
            self._purge(job_id)
        job = claim.job
        if job is None:
            return "idle"
        if job.base_model != self.config.base_model:
            raise WorkerError("WORKER_MODEL_MISMATCH")
        # Record a server-job namespace before any private training data is
        # written. After a process crash the next purge still has an exact path.
        self._purge(job.job_id)
        namespace = hashlib.sha256(job.job_id.encode()).hexdigest()[:16] + "-" + uuid4().hex[:16]
        directory = self.root / namespace
        directory.mkdir(mode=0o700)
        self.state["artifacts"][job.job_id] = namespace
        self._save()
        self.trainer.artifact_root = directory
        self.trainer.last_job_directory = None
        last_heartbeat, last_authorized = float("-inf"), False

        def authorized():
            nonlocal last_heartbeat, last_authorized
            now = self.clock()
            if now - last_heartbeat < 10:
                return last_authorized
            last_heartbeat = now
            try:
                response = self.transport.post(f"/internal/personal-learning/jobs/{job.job_id}/heartbeat", {
                    "worker_id": self.config.worker_id, "lease_token": job.lease_token})
                last_authorized = response.get("authorized") is True
            except (TransportError, ValueError):
                last_authorized = False
            return last_authorized

        # Each source/model fingerprint is rechecked by the server heartbeat.
        result = self.trainer.run(job.plan, authorization_check=authorized, policy=job.policy)
        output_directory = self.trainer.last_job_directory
        if output_directory is not None and output_directory.exists():
            if output_directory.parent.resolve() != directory.resolve():
                raise WorkerError("WORKER_TRAINER_OUTPUT_OUTSIDE_ROOT")
        if result.status == "revoked":
            self._purge(job.job_id)
        self.state["pending"] = {"job_id": job.job_id, "lease_token": job.lease_token,
                                 "result": TrainingResult.model_validate(result).model_dump(mode="json")}
        self._save()
        return result.status if self._upload_pending() else "result_waiting_for_server"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    worker = PersonalTrainingWorker(read_config(args.config))
    import fcntl
    lock = worker.root / ".personal-worker.lock"
    if lock.is_symlink():
        raise WorkerError("WORKER_LOCK_UNSAFE")
    handle = lock.open("a")
    os.chmod(lock, 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise WorkerError("WORKER_ALREADY_RUNNING") from None
    while True:
        try:
            status = worker.tick()
        except (WorkerError, ValueError, OSError):
            status = "worker_unavailable"
        if args.once or status != "idle":
            print(json.dumps({"status": status}), flush=True)
        if args.once:
            break
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except (WorkerError, ValueError, OSError):
        print('{"status":"worker_unavailable","reason":"private_config_or_runtime_invalid"}')
        raise SystemExit(1)
