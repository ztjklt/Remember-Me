# Private personal model training

This is a real local MLX LoRA adapter workflow. It updates a subject-specific
set of low-rank weights on a locally downloaded foundation model. It does not
modify the hosted DeepSeek model, upload personal records, activate a model, or
claim a personality-completion percentage.

`services/backend/app/personal_training.py` validates the private training
envelope, makes stable source-group splits and supervises the process. The API
must check the owner and a distinct active `MODEL_TRAINING` authorization before
creating a job. Its live callback must check that authorization, model version,
source basis, source availability and subject lifecycle while training and
again before accepting the result. A changed source or revoked grant stops the
process and deletes that job's data and adapters.

Only reviewed and confirmed original SUBJECT or CALIBRATION human targets are
eligible. The original target must match exactly. Third-party contributions,
AI inference and generated Twin/assistant replies cannot become training
targets. `source_group_id` must identify the original recording, complete call
or calibration source, so multiple snippets from that source stay together.

The default requires 40 examples, 10 independent sources, at least 24 training,
6 validation and 6 test examples. No augmentation fills an insufficient
dataset. A stable source hash reserves validation/test groups as new recordings
arrive; the caller can provide `source_partition` for a permanently sealed
benchmark. Exact copied targets crossing a holdout boundary are rejected.

The default job has batch size 1, 100 iterations, 2 LoRA layers, rank 8 and 512
tokens per sample. Training stops rather than silently truncating the original
answer. Limits cap steps, layers, sequence length, timeout and runtime log size.
The subprocess has no shell, no inherited provider credentials, offline Hugging
Face mode and no telemetry. Its worker additionally denies socket connections.
Datasets, logs and checkpoint files are private (0600 files, 0700 directories).

Install the optional runtime separately from the cloud API's Python environment:

```sh
uv venv --python 3.13 build/personal-training-venv
uv pip install --python build/personal-training-venv/bin/python -r tools/personal_training/requirements.txt
```

Download the public model separately before passing any personal data. The
tested compact model is the official
[Qwen3-0.6B MLX 4-bit model](https://huggingface.co/Qwen/Qwen3-0.6B-MLX-4bit).
Training itself accepts a local model path and performs no network operation.
MLX requires Apple silicon; an ordinary Linux cloud API reports unavailable and
keeps its retrieval-based Twin working. Other providers belong behind their own
adapters rather than being assumed available.

The local operator CLI takes an explicitly authorized private envelope with
`subject_id`, `actor_id`, `person_model_version`, `source_basis`,
`training_authorized: true`, `examples` and optional `policy`:

```sh
services/backend/.venv/bin/python tools/personal_training/run.py \
  --input /private/owner-authorized-job.json \
  --python build/personal-training-venv/bin/python \
  --model /private/local-model \
  --artifacts /private/personal-adapters \
  --output /private/job-result.json
```

Changing or deleting the CLI input envelope cancels its lease. A production
worker must use live server authorization instead of this operator-only lease.
CLI input is not a substitute for the server's consent checks.

## Automatic outbound worker

`worker.py` continuously claims owner-authorized jobs from the existing HTTPS
Backend. It requires a dedicated private configuration file, with mode **0600**
and owned by the current user. This example contains placeholders only; never
commit a completed configuration:

```json
{
  "origin": "https://YOUR_BACKEND_HOST",
  "secret": "REPLACE_WITH_PRIVATE_WORKER_SECRET_OF_AT_LEAST_32_CHARACTERS",
  "worker_id": "personal-trainer-mac",
  "local_model": "/absolute/path/to/prepared-mlx-model",
  "python": "/absolute/path/to/personal-training-venv/bin/python",
  "artifact_root": "/absolute/private/path/to/personal-training-artifacts",
  "base_model": "Qwen/Qwen3-0.6B-MLX-4bit"
}
```

```sh
chmod 600 /private/worker-config.json
services/backend/.venv/bin/python tools/personal_training/worker.py \
  --config /private/worker-config.json
```

`--once` sends one claim/heartbeat and handles at most one available job. Without
it the worker polls every 15 seconds while idle. During training it renews the
lease and rechecks live authorization every 10 seconds; each HTTPS request has
an 8-second timeout. A denied or failed heartbeat stops training and deletes
that job's data. A single-process file lock prevents two running workers from
using the same artifact state.

The secret is sent only in `X-Personal-Trainer-Secret`, never in a URL, job body,
log or the training subprocess's environment. Redirects and proxy environment
inheritance are disabled. The worker opens no inbound port. Completed results
are spooled privately until acknowledged by the Backend; a process restart can
retry them. Before writing personal training material it records a dedicated
server-job namespace. Backend `purge_job_ids` remove only recorded local
namespaces owned by that worker, including after a crash; arbitrary paths from
the server cannot trigger deletion.

This script does not install launchd jobs, Codex automations, cloud GPU services,
or paid providers. Starting it is a local operator action. Claims require the
Backend's distinct active model-training consent and valid reviewed source
basis. A local runtime's availability is not proof that a user's dataset is
sufficient or that a candidate can replace the hosted production model.

Results distinguish insufficient data, unavailable runtime, failed process,
revocation, held-out regression and a trained candidate. Success requires an
actual checkpoint, nonzero measured optimizer weight changes, and a finite
validation/test loss improvement of at least 1%. `activation_allowed` always
remains false: masked token loss only qualifies a candidate for an independent
blind personality evaluation, including factual attribution, uncertainty and
regression checks. It is not a reliable measure of human resemblance. Never
reuse a test set to optimize the next candidate or report a train-set score as
personality accuracy.

2026-10-14 synthetic-only smoke: on Apple M5 / 16 GB, official Qwen3-0.6B-MLX-4bit
with mlx-lm 0.30.7 / MLX 0.32.3 ran 12 optimizer steps over 59 training examples,
with 22 validation and 19 test examples from 100 fictitious independent sources.
360,448 LoRA parameters changed (delta L2 1.703568); a real safetensors checkpoint
was produced. Peak MLX allocator memory was 500,219,068 bytes. Formulaic-task
validation loss went from 4.595737 to 0.001789; test loss from 4.568904 to 0.001776.
This proves the training path, not real-user fidelity. No real personal material
was used and no production model was switched. Private raw artifacts stay under
`build/private/personal-training-smoke`; the safe run log is
`build/personal-training-smoke.log`.

Implementation references: [official MLX LM fine-tuning guidance](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)
and [official MLX LM tuner](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/tuner/trainer.py).
