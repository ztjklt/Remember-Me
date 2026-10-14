"""Local worker protocol tests with fake transport and no personal data."""
import json
import os
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from worker import (PersonalTrainingWorker, TransportError, WorkerConfig, WorkerError,
                    _NoRedirect, read_config)
from app.personal_training import (TrainingCapability, TrainingExample, TrainingMetrics,
                                   TrainingPolicy, TrainingResult, prepare_dataset)


def config(tmp_path):
    return WorkerConfig(origin="https://example.invalid", secret="synthetic-not-a-real-secret" * 2,
        worker_id="test-worker", local_model=tmp_path / "model", python=Path(sys.executable),
        artifact_root=tmp_path / "artifacts")


def job():
    examples = []
    for n in range(100):
        target = f"第 {n} 条合成原话。"
        examples.append(TrainingExample(example_id=f"e{n}", subject_id="synthetic-person", actor_id="owner",
            owner_actor_id="owner", source_group_id=f"source{n}", source_ref=f"episode:source{n}",
            source_type="SUBJECT", target_origin="human", verified=True, confirmed=True,
            prompt=f"合成问题 {n}？", target=target, verified_target=target))
    policy = TrainingPolicy(iterations=1)
    plan = prepare_dataset(examples, subject_id="synthetic-person", actor_id="owner",
        person_model_version="v1", source_basis="b1", policy=policy)
    return {"job_id": "job-test-1", "lease_token": "synthetic-lease", "base_model": "Qwen/Qwen3-0.6B-MLX-4bit",
            "plan": plan.model_dump(mode="json"), "policy": policy.model_dump()}


class FakeTransport:
    def __init__(self, claimed=None):
        self.claimed = claimed
        self.calls = []
        self.purge = []
        self.authorized = True
        self.result_failures = 0

    def post(self, endpoint, body):
        self.calls.append((endpoint, body))
        if endpoint.endswith("/claim"):
            claimed, self.claimed = self.claimed, None
            return {"job": claimed, "purge_job_ids": self.purge}
        if endpoint.endswith("/heartbeat"):
            if self.authorized is False:
                raise TransportError("synthetic-denied", http_status=403)
            return {"authorized": True}
        if endpoint.endswith("/result"):
            if self.result_failures:
                self.result_failures -= 1
                raise TransportError("synthetic-unavailable", http_status=503)
            return {"status": "received"}
        raise AssertionError("Unexpected fake endpoint")


def test_cleanup_continues_after_more_than_two_hundred_historical_revocations(tmp_path):
    transport = FakeTransport()
    transport.purge = [f"revoked-job-{n}" for n in range(201)]
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert worker.tick() == "idle"


class FakeTrainer:
    artifact_root = None
    last_job_directory = None

    def capability(self):
        return TrainingCapability(available=True, reason="available")

    def run(self, plan, *, authorization_check, policy):
        allowed = authorization_check()
        common = dict(subject_id=plan.subject_id, person_model_version=plan.person_model_version,
            source_basis=plan.source_basis, dataset_sha256=plan.dataset_sha256,
            train_count=len(plan.train), validation_count=len(plan.validation), test_count=len(plan.test))
        if not allowed:
            return TrainingResult(status="revoked", reason="authorization_or_sources_changed", **common)
        self.last_job_directory = self.artifact_root / ("a" * 32)
        self.last_job_directory.mkdir(mode=0o700)
        path = self.last_job_directory / "synthetic-checkpoint"
        path.write_text("test fixture only")
        os.chmod(path, 0o600)
        return TrainingResult(status="trained", reason="synthetic_test_only", **common,
            metrics=TrainingMetrics(baseline_validation_loss=2, validation_loss=1,
                baseline_test_loss=2, test_loss=1, weight_delta_l2=1, optimizer_steps=1,
                trainable_parameter_count=10, peak_memory_bytes=1024, mlx_lm_version="fixture"),
            adapter_sha256="a" * 64)


def test_config_requires_private_regular_owner_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(config(tmp_path).model_dump_json())
    os.chmod(path, 0o644)
    with pytest.raises(WorkerError, match="0600"):
        read_config(path)
    os.chmod(path, 0o600)
    assert read_config(path).worker_id == "test-worker"
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(WorkerError):
        read_config(link)
    assert "synthetic-not-a-real-secret" not in repr(read_config(path))


@pytest.mark.parametrize("origin", ["http://example.invalid", "https://name:pass@example.invalid",
    "https://example.invalid/?secret=x", "https://example.invalid/path"])
def test_origin_cannot_redirect_or_embed_credential(tmp_path, origin):
    with pytest.raises(ValidationError):
        WorkerConfig.model_validate({**config(tmp_path).model_dump(), "origin": origin})
    with pytest.raises(TransportError, match="REDIRECT_REJECTED"):
        _NoRedirect().redirect_request(None, None, 302, "", {}, "https://another.invalid")


def test_idle_heartbeat_and_no_training(tmp_path):
    transport, trainer = FakeTransport(), FakeTrainer()
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=trainer)
    assert worker.tick() == "idle"
    assert transport.calls[0][1] == {"worker_id": "test-worker",
        "base_model": "Qwen/Qwen3-0.6B-MLX-4bit", "available": True}
    assert trainer.last_job_directory is None


def test_claim_train_heartbeat_result_without_secret_in_bodies(tmp_path):
    transport = FakeTransport(job())
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert worker.tick() == "trained"
    assert any(endpoint.endswith("/heartbeat") for endpoint, _ in transport.calls)
    result = transport.calls[-1][1]["result"]
    assert result["activation_allowed"] is False
    assert "synthetic-not-a-real-secret" not in json.dumps(transport.calls)
    assert worker.state["pending"] is None
    assert worker.state_path.stat().st_mode & 0o777 == 0o600


def test_revoked_heartbeat_purges_before_upload(tmp_path):
    transport = FakeTransport(job())
    transport.authorized = False
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert worker.tick() == "revoked"
    assert worker.state["artifacts"] == {}
    assert transport.calls[-1][1]["result"]["status"] == "revoked"


def test_pending_result_retries_after_worker_restart(tmp_path):
    transport = FakeTransport(job())
    transport.result_failures = 1
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert worker.tick() == "result_waiting_for_server"
    assert worker.state["pending"]
    restarted = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert restarted.tick() == "idle"
    assert restarted.state["pending"] is None
    assert len([endpoint for endpoint, _ in transport.calls if endpoint.endswith("/result")]) == 2


def test_server_purge_deletes_only_recorded_own_namespace(tmp_path):
    transport = FakeTransport(job())
    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=FakeTrainer())
    assert worker.tick() == "trained"
    own = worker.root / worker.state["artifacts"]["job-test-1"]
    unrelated = worker.root / "unrelated-owner-artifact"
    unrelated.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("keep")
    transport.purge = ["job-test-1", "../outside", "unknown-job"]
    assert worker.tick() == "idle"
    assert not own.exists() and unrelated.exists() and outside.exists()


def test_other_worker_cannot_read_or_purge_state(tmp_path):
    PersonalTrainingWorker(config(tmp_path), transport=FakeTransport(), trainer=FakeTrainer())
    other = config(tmp_path).model_copy(update={"worker_id": "different-worker"})
    with pytest.raises(WorkerError, match="OWNER_MISMATCH"):
        PersonalTrainingWorker(other, transport=FakeTransport(), trainer=FakeTrainer())


def test_training_heartbeat_caching_sends_at_most_every_ten_seconds(tmp_path):
    clock = [0.0]
    transport = FakeTransport(job())

    class PollingTrainer(FakeTrainer):
        def run(self, plan, *, authorization_check, policy):
            for seconds in (0, 0.25, 5, 10, 10.25, 19, 20):
                clock[0] = seconds
                assert authorization_check()
            return super().run(plan, authorization_check=authorization_check, policy=policy)

    worker = PersonalTrainingWorker(config(tmp_path), transport=transport, trainer=PollingTrainer(),
                                    monotonic=lambda: clock[0])
    assert worker.tick() == "trained"
    assert len([e for e, _ in transport.calls if e.endswith("/heartbeat")]) == 3
