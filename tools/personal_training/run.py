"""Local operator entry point. Inputs and outputs are private files.

This CLI does not fetch personal data, bypass consent, or switch production
models. A server worker should provide a live authorization callback instead.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "backend"))
from app.personal_training import MLXLoRATrainer, TrainingExample, TrainingPolicy, prepare_dataset
from pydantic import ValidationError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="Owner-authorized private JSON envelope")
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="Already downloaded local MLX model")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.input.stat().st_size > 16 * 1024 * 1024:
        raise SystemExit("TRAINING_INPUT_TOO_LARGE")
    original_bytes = args.input.read_bytes()
    envelope = json.loads(original_bytes)
    policy = TrainingPolicy.model_validate(envelope.get("policy", {}))
    scope = {key: envelope[key] for key in ("subject_id", "actor_id", "person_model_version", "source_basis")}
    plan = prepare_dataset([TrainingExample.model_validate(e) for e in envelope["examples"]], **scope, policy=policy)

    def authorized():
        # The local operator's lease is private; deletion/revocation cancels the job.
        current_bytes = args.input.read_bytes() if args.input.is_file() else b"{}"
        current = json.loads(current_bytes)
        return (current_bytes == original_bytes and current.get("training_authorized") is True and
                all(current.get(k) == value for k, value in scope.items()))

    trainer = MLXLoRATrainer(python=args.python, model=args.model,
        worker=Path(__file__).with_name("mlx_job.py"), artifact_root=args.artifacts)
    result = trainer.run(plan, authorization_check=authorized, policy=policy)
    with args.output.open("x") as handle:
        os.chmod(args.output, 0o600)
        handle.write(result.model_dump_json(indent=2))
    print(json.dumps({"status": result.status, "reason": result.reason,
                      "activation_allowed": result.activation_allowed}))


if __name__ == "__main__":
    try:
        main()
    except (ValidationError, ValueError, KeyError, OSError):
        # Validation exceptions can contain a complete input record; do not log it.
        print('{"status":"failed","reason":"training_input_or_runtime_invalid"}')
        raise SystemExit(1)
