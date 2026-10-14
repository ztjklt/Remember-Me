"""Provenance, stable holdout, actual subprocess boundaries and fail-closed gates."""
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

from app.personal_training import (MLXLoRATrainer, TrainingCapability, TrainingExample,
                                   TrainingPolicy, TrainingValidationError, prepare_dataset)


def example(n, **changes):
    target = f"本人核对的第 {n} 条回答。"
    value = dict(example_id=f"e{n}", subject_id="s1", actor_id="a1", owner_actor_id="a1",
        source_group_id=f"episode{n}", source_ref=f"episode:episode{n}#verified",
        source_type="SUBJECT", target_origin="human", verified=True, confirmed=True,
        prompt=f"第 {n} 条问题？", target=target, verified_target=target)
    value.update(changes)
    return TrainingExample.model_validate(value)


def plan(examples=None, policy=None):
    return prepare_dataset(examples or [example(i) for i in range(100)], subject_id="s1",
        actor_id="a1", person_model_version="v1", source_basis="basis1", policy=policy)


@pytest.mark.parametrize("changes", [
    {"source_type": "THIRD_PARTY"}, {"source_type": "AI_INFERENCE"},
    {"target_origin": "assistant"}, {"verified": False}, {"confirmed": False},
    {"owner_actor_id": "another-owner"}, {"target": "A generated paraphrase."},
])
def test_unverified_or_generated_targets_rejected(changes):
    with pytest.raises(ValidationError):
        example(1, **changes)


def test_owner_calibration_original_is_eligible():
    assert example(1, source_type="CALIBRATION").source_type == "CALIBRATION"


def test_subject_actor_isolation_and_duplicate_ids():
    for rows in ([example(1, subject_id="s2")], [example(1, actor_id="a2", owner_actor_id="a2")],
                 [example(1), example(1)]):
        with pytest.raises(TrainingValidationError):
            plan(rows)


def test_source_group_holdout_is_permanent_as_new_sources_arrive():
    initial = plan([example(i) for i in range(50)])
    expanded = plan()
    mapping = lambda p: {e.source_group_id: name for name in ("train", "validation", "test")
                         for e in getattr(p, name)}
    assert all(mapping(expanded)[source] == split for source, split in mapping(initial).items())
    assert plan(list(reversed([example(i) for i in range(100)]))) == expanded
    assert set(e.source_group_id for e in expanded.train).isdisjoint(
        e.source_group_id for e in expanded.test + expanded.validation)


def test_same_episode_never_crosses_partitions_and_sealed_partition_respected():
    rows = [example(1, source_group_id="sealed", source_partition="test"),
            example(2, source_group_id="sealed")]
    assert len(plan(rows).test) == 2
    with pytest.raises(TrainingValidationError, match="PARTITION_CONFLICT"):
        plan([*rows, example(3, source_group_id="sealed", source_partition="train")])


def test_copied_human_target_cannot_leak_to_holdout():
    target = "我喜欢喝不加糖的茶。"
    with pytest.raises(TrainingValidationError, match="DUPLICATE_ACROSS_HOLDOUT"):
        plan([example(1, target=target, verified_target=target, source_partition="train"),
              example(2, target=target, verified_target=target, source_partition="test")])


def test_small_or_single_source_dataset_never_trains(tmp_path):
    p = plan([example(i, source_group_id="single-call") for i in range(100)])
    assert p.status == "insufficient_data"
    assert "independent_sources" in p.missing
    trainer = MLXLoRATrainer(python=Path(sys.executable), model=tmp_path, worker=tmp_path / "missing",
                           artifact_root=tmp_path / "artifacts")
    result = trainer.run(p, authorization_check=lambda: True)
    assert result.status == "insufficient_data"
    assert not result.activation_allowed
    assert not (tmp_path / "artifacts").exists()


def test_plan_scope_version_and_text_change_fingerprints():
    p = plan()
    changed = prepare_dataset([example(i) for i in range(100)], subject_id="s1", actor_id="a1",
                              person_model_version="v2", source_basis="basis2")
    assert p.dataset_sha256 != changed.dataset_sha256


def trainer_fixture(tmp_path, monkeypatch, *, improved=True, metrics_valid=True, sleep=False):
    worker = tmp_path / "worker.py"
    worker.write_text('''import argparse,json,os,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--model');p.add_argument('--job');a=p.parse_args()
job=Path(a.job)
assert os.environ['HF_HUB_OFFLINE']=='1'
assert os.environ['HF_HUB_DISABLE_TELEMETRY']=='1'
assert 'SECRET_TEST_TOKEN' not in os.environ
''' + ("time.sleep(5)\n" if sleep else "") + '''
(job/'adapter').mkdir()
(job/'adapter'/'adapters.safetensors').write_bytes(b'test fixture, not MLX weights')
metrics=dict(baseline_validation_loss=2.0, validation_loss=LOSS,
 baseline_test_loss=2.0,test_loss=LOSS,weight_delta_l2=DELTA,optimizer_steps=1,
 trainable_parameter_count=200,peak_memory_bytes=1024,mlx_lm_version='fixture')
(job/'metrics.json').write_text(json.dumps(metrics))
'''.replace("LOSS", "1.5" if improved else "2.1").replace("DELTA", "1.0" if metrics_valid else "0.0"))
    trainer = MLXLoRATrainer(python=Path(sys.executable), model=tmp_path, worker=worker,
                           artifact_root=tmp_path / "private-artifacts")
    monkeypatch.setattr(trainer, "capability", lambda: TrainingCapability(available=True, reason="available"))
    return trainer


def test_runtime_capability_fallback_not_success(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(trainer, "capability", lambda: TrainingCapability(available=False, reason="runtime_missing"))
    assert trainer.run(plan(), authorization_check=lambda: True).status == "unavailable"


def test_caller_cannot_forge_ready_or_changed_plan(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch)
    forged = plan().model_copy(update={"source_basis": "forged"})
    with pytest.raises(TrainingValidationError, match="PLAN_CHANGED"):
        trainer.run(forged, authorization_check=lambda: True)


def test_subprocess_private_outputs_secret_free_environment_and_no_activation(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TEST_TOKEN", "must never reach trainer")
    trainer = trainer_fixture(tmp_path, monkeypatch)
    policy = TrainingPolicy(iterations=1)
    result = trainer.run(plan(policy=policy), authorization_check=lambda: True, policy=policy)
    assert result.status == "trained"
    assert result.adapter_sha256 and result.metrics.weight_delta_l2 > 0
    assert not result.activation_allowed and result.requires_personality_evaluation
    for path in trainer.last_job_directory.rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)


def test_heldout_regression_keeps_candidate_rejected(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch, improved=False)
    policy = TrainingPolicy(iterations=1)
    result = trainer.run(plan(policy=policy), authorization_check=lambda: True, policy=policy)
    assert result.status == "rejected"
    assert result.reason == "heldout_loss_did_not_improve"


def test_no_weight_change_is_failure_even_with_good_loss(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch, metrics_valid=False)
    policy = TrainingPolicy(iterations=1)
    result = trainer.run(plan(policy=policy), authorization_check=lambda: True, policy=policy)
    assert result.status == "failed" and result.adapter_sha256 is None
    assert not (trainer.last_job_directory / "adapter").exists()


def test_revocation_during_process_kills_and_deletes_private_training_data(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch, sleep=True)
    calls = 0

    def authorized():
        nonlocal calls
        calls += 1
        return calls < 4

    result = trainer.run(plan(), authorization_check=authorized)
    assert result.status == "revoked" and result.metrics is None
    assert not trainer.last_job_directory.exists()


def test_lost_authorization_service_is_fail_closed(tmp_path, monkeypatch):
    trainer = trainer_fixture(tmp_path, monkeypatch)

    def broken():
        raise RuntimeError("connection details must not be returned")

    result = trainer.run(plan(), authorization_check=broken)
    assert result.status == "revoked"
    assert not (tmp_path / "private-artifacts").exists()
