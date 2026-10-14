"""Private, bounded personal LoRA jobs; training never activates a model.

The API/worker owns consent and current-source checks. This module accepts only
verified human targets and rechecks that authorization while a local subprocess
updates weights. It contains no remote-provider or upload path.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time
from typing import Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingValidationError(ValueError):
    """A safe code, never the rejected personal text."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrainingExample(StrictModel):
    example_id: str = Field(min_length=1, max_length=128)
    subject_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    owner_actor_id: str = Field(min_length=1, max_length=128)
    source_group_id: str = Field(min_length=1, max_length=128)
    source_partition: Literal["train", "validation", "test"] | None = None
    source_ref: str = Field(min_length=1, max_length=1024)
    source_type: Literal["SUBJECT", "CALIBRATION"]
    target_origin: Literal["human"]
    verified: Literal[True]
    confirmed: Literal[True]
    prompt: str = Field(min_length=1, max_length=4000)
    target: str = Field(min_length=1, max_length=8000)
    verified_target: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def human_owner_only(self):
        if self.actor_id != self.owner_actor_id:
            raise ValueError("TRAINING_OWNER_REQUIRED")
        if not self.prompt.strip() or not self.target.strip():
            raise ValueError("TRAINING_EMPTY_TEXT")
        # A generated paraphrase must not replace the reviewed original target.
        if self.target != self.verified_target:
            raise ValueError("TRAINING_TARGET_NOT_ORIGINAL")
        return self


class TrainingPolicy(StrictModel):
    min_examples: int = Field(default=40, ge=3, le=10000)
    min_source_groups: int = Field(default=10, ge=3, le=10000)
    min_train: int = Field(default=24, ge=1, le=10000)
    min_validation: int = Field(default=6, ge=1, le=10000)
    min_test: int = Field(default=6, ge=1, le=10000)
    max_examples: int = Field(default=2000, ge=3, le=10000)
    iterations: int = Field(default=100, ge=1, le=1000)
    num_layers: int = Field(default=2, ge=1, le=8)
    rank: int = Field(default=8, ge=1, le=32)
    learning_rate: float = Field(default=0.0001, gt=0, le=0.001)
    max_seq_length: int = Field(default=512, ge=64, le=2048)
    timeout_seconds: int = Field(default=1800, ge=10, le=3600)
    minimum_relative_loss_improvement: float = Field(default=0.01, ge=0, le=0.5)
    seed: int = Field(default=17, ge=0, le=2147483647)


class DatasetPlan(StrictModel):
    status: Literal["ready", "insufficient_data"]
    subject_id: str
    actor_id: str
    person_model_version: str
    source_basis: str
    dataset_sha256: str
    source_group_count: int
    train: tuple[TrainingExample, ...]
    validation: tuple[TrainingExample, ...]
    test: tuple[TrainingExample, ...]
    missing: tuple[str, ...] = ()


class TrainingCapability(StrictModel):
    available: bool
    reason: Literal["available", "apple_silicon_required", "runtime_missing", "model_missing"]


class TrainingMetrics(StrictModel):
    baseline_validation_loss: float = Field(ge=0, allow_inf_nan=False)
    validation_loss: float = Field(ge=0, allow_inf_nan=False)
    baseline_test_loss: float = Field(ge=0, allow_inf_nan=False)
    test_loss: float = Field(ge=0, allow_inf_nan=False)
    weight_delta_l2: float = Field(gt=0, allow_inf_nan=False)
    optimizer_steps: int = Field(ge=1, le=1000)
    trainable_parameter_count: int = Field(gt=0)
    peak_memory_bytes: int = Field(ge=0)
    mlx_lm_version: str = Field(min_length=1, max_length=32)


class TrainingResult(StrictModel):
    status: Literal["insufficient_data", "unavailable", "failed", "revoked", "rejected", "trained"]
    reason: str = Field(min_length=1, max_length=100)
    subject_id: str
    person_model_version: str
    source_basis: str
    dataset_sha256: str
    train_count: int
    validation_count: int
    test_count: int
    metrics: TrainingMetrics | None = None
    adapter_sha256: str | None = None
    # Held-out token loss is a prerequisite, not proof of person fidelity.
    activation_allowed: Literal[False] = False
    requires_personality_evaluation: Literal[True] = True


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: str) -> str:
    return " ".join(value.split()).casefold()


def prepare_dataset(examples: list[TrainingExample], *, subject_id: str,
                    actor_id: str, person_model_version: str, source_basis: str,
                    policy: TrainingPolicy | None = None) -> DatasetPlan:
    """Keep a whole original Episode/call/calibration on one split.

    A stable source hash preserves held-out groups as new recordings arrive.
    The caller can provide sealed benchmark partitions. Copied targets crossing
    partitions are rejected, rather than improving the apparent evaluation.
    """
    policy = policy or TrainingPolicy()
    if not all((subject_id, actor_id, person_model_version, source_basis)):
        raise TrainingValidationError("TRAINING_SCOPE_REQUIRED")
    if len(examples) > policy.max_examples:
        raise TrainingValidationError("TRAINING_DATASET_TOO_LARGE")
    checked = [TrainingExample.model_validate(e.model_dump()) for e in examples]
    if any(e.subject_id != subject_id or e.actor_id != actor_id for e in checked):
        raise TrainingValidationError("TRAINING_SCOPE_MISMATCH")
    if len({e.example_id for e in checked}) != len(checked):
        raise TrainingValidationError("TRAINING_DUPLICATE_ID")
    checked.sort(key=lambda e: e.example_id)
    groups: dict[str, list[TrainingExample]] = {}
    for e in checked:
        groups.setdefault(e.source_group_id, []).append(e)
    keys = sorted(groups, key=lambda g: _digest(f"personal-training-v1:{subject_id}:{g}"))
    assignments = {}
    for group, rows in groups.items():
        specified = {e.source_partition for e in rows if e.source_partition is not None}
        if len(specified) > 1:
            raise TrainingValidationError("TRAINING_SOURCE_PARTITION_CONFLICT")
        bucket = int(_digest(f"personal-training-v1:{subject_id}:{group}"), 16) % 10
        assignments[group] = (next(iter(specified)) if specified else
                              "validation" if bucket < 2 else "test" if bucket < 4 else "train")
    targets: dict[str, str] = {}
    for e in checked:
        key, split = _digest(_canonical(e.target)), assignments[e.source_group_id]
        if key in targets and targets[key] != split:
            raise TrainingValidationError("TRAINING_DUPLICATE_ACROSS_HOLDOUT")
        targets[key] = split
    splits: dict[str, list[TrainingExample]] = {"train": [], "validation": [], "test": []}
    for group in keys:
        splits[assignments[group]].extend(groups[group])
    missing = []
    if len(checked) < policy.min_examples:
        missing.append("examples")
    if len(groups) < policy.min_source_groups:
        missing.append("independent_sources")
    for split, minimum in (("train", policy.min_train), ("validation", policy.min_validation),
                           ("test", policy.min_test)):
        if len(splits[split]) < minimum:
            missing.append(split)
    fingerprint = _digest(json.dumps({"schema": "personal-training-v1", "subject": subject_id,
        "actor": actor_id, "version": person_model_version, "basis": source_basis,
        "splits": {k: [e.model_dump() for e in v] for k, v in splits.items()}},
        sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    return DatasetPlan(status="insufficient_data" if missing else "ready", subject_id=subject_id,
        actor_id=actor_id, person_model_version=person_model_version, source_basis=source_basis,
        dataset_sha256=fingerprint, source_group_count=len(groups),
        train=tuple(splits["train"]), validation=tuple(splits["validation"]),
        test=tuple(splits["test"]), missing=tuple(missing))


def _private_write(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        handle.write(value)


class MLXLoRATrainer:
    """Local runtime adapter. A Linux cloud API reports unavailable honestly."""

    def __init__(self, *, python: Path, model: Path, worker: Path, artifact_root: Path):
        self.python, self.model, self.worker = python.absolute(), model.absolute(), worker.absolute()
        self.artifact_root = artifact_root.absolute()
        self.last_job_directory: Path | None = None

    def capability(self) -> TrainingCapability:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            return TrainingCapability(available=False, reason="apple_silicon_required")
        if not self.python.is_file() or not self.worker.is_file():
            return TrainingCapability(available=False, reason="runtime_missing")
        if not (self.model / "config.json").is_file() or not list(self.model.glob("*.safetensors")):
            return TrainingCapability(available=False, reason="model_missing")
        return TrainingCapability(available=True, reason="available")

    def run(self, plan: DatasetPlan, *, authorization_check: Callable[[], bool],
            policy: TrainingPolicy | None = None) -> TrainingResult:
        """Caller rechecks consent, owner, model version and source basis."""
        policy = policy or TrainingPolicy()
        def authorized() -> bool:
            try:
                return authorization_check() is True
            except Exception:
                # Losing the authorization service must stop weight updates.
                return False
        common = dict(subject_id=plan.subject_id, person_model_version=plan.person_model_version,
            source_basis=plan.source_basis, dataset_sha256=plan.dataset_sha256,
            train_count=len(plan.train), validation_count=len(plan.validation), test_count=len(plan.test))
        if not authorized():
            return TrainingResult(status="revoked", reason="authorization_or_sources_changed", **common)
        if plan.status != "ready":
            return TrainingResult(status="insufficient_data", reason="verified_human_data_required", **common)
        # Do not trust a caller-crafted ready plan or a changed policy.
        rebuilt = prepare_dataset(list(plan.train + plan.validation + plan.test),
            subject_id=plan.subject_id, actor_id=plan.actor_id,
            person_model_version=plan.person_model_version, source_basis=plan.source_basis, policy=policy)
        if rebuilt != plan:
            raise TrainingValidationError("TRAINING_PLAN_CHANGED")
        capability = self.capability()
        if not capability.available:
            return TrainingResult(status="unavailable", reason=capability.reason, **common)
        root = self.artifact_root
        if root.is_symlink():
            raise TrainingValidationError("TRAINING_UNSAFE_ARTIFACT_ROOT")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        job = root / (_digest(plan.subject_id)[:16] + "-" + _digest(plan.person_model_version)[:12]
                      + "-" + plan.dataset_sha256[:12] + "-" + uuid4().hex[:12])
        job.mkdir(mode=0o700)
        self.last_job_directory = job
        data = job / "dataset"
        data.mkdir(mode=0o700)
        for name, rows in (("train", plan.train), ("valid", plan.validation), ("test", plan.test)):
            payload = "".join(json.dumps({"messages": [
                {"role": "system", "content": "依据本人已核对的资料，以第一人称回答；未知事实保持未知。"},
                {"role": "user", "content": row.prompt},
                {"role": "assistant", "content": row.target}]}, ensure_ascii=False) + "\n" for row in rows)
            _private_write(data / f"{name}.jsonl", payload)
        _private_write(job / "manifest.json", json.dumps({**common,
            "source_group_count": plan.source_group_count,
            "source_refs": [e.source_ref for e in plan.train + plan.validation + plan.test]}, ensure_ascii=False))
        _private_write(job / "policy.json", policy.model_dump_json())
        (job / "home").mkdir(mode=0o700)
        (job / "tmp").mkdir(mode=0o700)
        environment = {"PATH": os.defpath, "HOME": str(job / "home"), "TMPDIR": str(job / "tmp"),
            "LANG": "en_US.UTF-8", "PYTHONNOUSERSITE": "1", "PYTHONUNBUFFERED": "1",
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1", "WANDB_DISABLED": "true", "WANDB_MODE": "disabled",
            "TOKENIZERS_PARALLELISM": "false"}
        argv = [str(self.python), "-I", str(self.worker), "--model", str(self.model),
                "--job", str(job)]
        status, reason, metrics, adapter_hash = "failed", "training_process_failed", None, None
        process = None
        started = time.monotonic()
        try:
            with (job / "runtime.log").open("xb") as log:
                os.chmod(job / "runtime.log", 0o600)
                process = subprocess.Popen(argv, shell=False, cwd=job, env=environment,
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                while process.poll() is None:
                    if not authorized():
                        status, reason = "revoked", "authorization_or_sources_changed"
                        break
                    if time.monotonic() - started > policy.timeout_seconds:
                        reason = "training_timeout"
                        break
                    if (job / "runtime.log").stat().st_size > 2 * 1024 * 1024:
                        reason = "training_log_limit"
                        break
                    time.sleep(0.25)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                elif process.returncode == 0:
                    raw = (job / "metrics.json").read_bytes()
                    if len(raw) > 16384:
                        raise ValueError("metrics_limit")
                    metrics = TrainingMetrics.model_validate_json(raw)
                    if metrics.optimizer_steps != policy.iterations:
                        raise ValueError("optimizer_step_mismatch")
                    adapter = job / "adapter" / "adapters.safetensors"
                    if adapter.is_symlink() or not adapter.is_file() or adapter.stat().st_size == 0:
                        raise ValueError("checkpoint_missing")
                    adapter_hash = hashlib.sha256(adapter.read_bytes()).hexdigest()
                    validation_improvement = ((metrics.baseline_validation_loss - metrics.validation_loss)
                        / max(metrics.baseline_validation_loss, 1e-12))
                    test_improvement = ((metrics.baseline_test_loss - metrics.test_loss)
                        / max(metrics.baseline_test_loss, 1e-12))
                    if min(validation_improvement, test_improvement) >= policy.minimum_relative_loss_improvement:
                        status, reason = "trained", "heldout_loss_improved_personality_evaluation_required"
                    else:
                        status, reason = "rejected", "heldout_loss_did_not_improve"
        except (OSError, ValueError, subprocess.SubprocessError):
            # Runtime logs stay private; API responses never contain raw model output.
            reason = "training_process_or_metrics_invalid"
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            if not authorized():
                status, reason, metrics, adapter_hash = "revoked", "authorization_or_sources_changed", None, None
            if status == "revoked":
                shutil.rmtree(job)
            else:
                for path in job.rglob("*"):
                    if path.is_symlink():
                        status, reason, adapter_hash = "failed", "unsafe_artifact", None
                        path.unlink()
                    else:
                        os.chmod(path, 0o700 if path.is_dir() else 0o600)
                if status == "failed":
                    shutil.rmtree(job / "adapter", ignore_errors=True)
        return TrainingResult(status=status, reason=reason, metrics=metrics,
                              adapter_sha256=adapter_hash, **common)
