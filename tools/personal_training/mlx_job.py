"""Offline subprocess implementation; invoked by MLXLoRATrainer only.

Uses the official mlx-lm 0.30 tuner API. The source model stays unchanged;
per-subject LoRA matrices undergo actual optimizer updates.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import socket


def _deny_network(*_args, **_kwargs):
    raise RuntimeError("PERSONAL_TRAINING_NETWORK_DISABLED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    # Even a dependency accidentally trying telemetry cannot send training data.
    socket.socket.connect = _deny_network
    socket.socket.connect_ex = _deny_network
    socket.create_connection = _deny_network
    import mlx.core as mx
    import mlx.optimizers as optim
    from mlx.utils import tree_flatten
    from mlx_lm import load
    from mlx_lm.tuner.datasets import CacheDataset, ChatDataset
    from mlx_lm.tuner.callbacks import TrainingCallback
    from mlx_lm.tuner.trainer import TrainingArgs, evaluate, train
    from mlx_lm.tuner.utils import linear_to_lora_layers

    policy = json.loads((args.job / "policy.json").read_text())
    mx.random.seed(policy["seed"])
    model, tokenizer = load(str(args.model), tokenizer_config={"trust_remote_code": False})

    def dataset(name):
        rows = [json.loads(line) for line in (args.job / "dataset" / f"{name}.jsonl").read_text().splitlines()]
        result = CacheDataset(ChatDataset(rows, tokenizer, mask_prompt=True))
        # Truncating away the human target could produce a fake zero-loss job.
        for i in range(len(result)):
            tokens, offset = result[i]
            if len(tokens) > policy["max_seq_length"] or offset >= len(tokens) - 1:
                raise ValueError("TRAINING_SAMPLE_TOO_LONG_OR_EMPTY_TARGET")
        return result

    train_set, valid_set, test_set = dataset("train"), dataset("valid"), dataset("test")

    def loss(rows):
        model.eval()
        # Evaluate every held-out row with prompt masking; no gradient updates.
        return float(evaluate(model, rows, batch_size=1, num_batches=-1,
                              max_seq_length=policy["max_seq_length"]))

    baseline_validation_loss, baseline_test_loss = loss(valid_set), loss(test_set)
    model.freeze()
    lora_parameters = {"rank": policy["rank"], "dropout": 0.0, "scale": 20.0}
    linear_to_lora_layers(model, policy["num_layers"], lora_parameters)
    initial = {k: mx.array(v) for k, v in tree_flatten(model.trainable_parameters())}
    mx.eval(initial)
    trainable_parameter_count = sum(v.size for v in initial.values())
    adapter_dir = args.job / "adapter"
    adapter_dir.mkdir(mode=0o700)
    adapter_file = adapter_dir / "adapters.safetensors"
    adapter_config = {"fine_tune_type": "lora", "num_layers": policy["num_layers"],
                      "lora_parameters": lora_parameters}
    (adapter_dir / "adapter_config.json").write_text(json.dumps(adapter_config))
    steps = policy["iterations"]
    class StepCounter(TrainingCallback):
        completed = 0

        def on_train_loss_report(self, info):
            self.completed = int(info["iteration"])

    counter = StepCounter()
    training_args = TrainingArgs(batch_size=1, iters=steps, val_batches=-1,
        steps_per_report=max(1, min(10, steps)), steps_per_eval=steps,
        steps_per_save=steps, adapter_file=str(adapter_file),
        max_seq_length=policy["max_seq_length"], grad_checkpoint=True)
    model.train()
    train(model=model, args=training_args, optimizer=optim.Adam(learning_rate=policy["learning_rate"]),
          train_dataset=train_set, val_dataset=valid_set, training_callback=counter)
    if counter.completed != steps:
        raise ValueError("TRAINING_OPTIMIZER_STEPS_INCOMPLETE")
    final = dict(tree_flatten(model.trainable_parameters()))
    delta_squared = sum(mx.sum((final[k].astype(mx.float32) - v.astype(mx.float32)) ** 2)
                        for k, v in initial.items())
    weight_delta_l2 = float(mx.sqrt(delta_squared))
    validation_loss, test_loss = loss(valid_set), loss(test_set)
    metrics = dict(baseline_validation_loss=baseline_validation_loss,
        validation_loss=validation_loss, baseline_test_loss=baseline_test_loss,
        test_loss=test_loss, weight_delta_l2=weight_delta_l2, optimizer_steps=counter.completed,
        trainable_parameter_count=trainable_parameter_count,
        peak_memory_bytes=mx.get_peak_memory(), mlx_lm_version=importlib.metadata.version("mlx-lm"))
    (args.job / "metrics.json").write_text(json.dumps(metrics, allow_nan=False))


if __name__ == "__main__":
    main()
