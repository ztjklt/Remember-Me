# AI Core Service

The shared AI Core supports Phase 1 and the Product Owner's approved iOS Person Model slice. Current ownership follows the [two-client delivery model](../../docs/team/00_TEAM_OWNERSHIP.md); the original [task brief](../../docs/team/02_KANGXIN_AI_CORE.md) records the Phase 1 foundation.

The current iOS deployment uses `AI_PROVIDER=deepseek` with `AI_MODEL=deepseek-v4-flash`. This sends the transcript, but not the audio, to DeepSeek over HTTPS. The model supplies an original quote and a domain; Python resolves a corresponding span in the original Chinese transcript and drops any candidate it cannot locate. The actual API response model name is stored with each extraction. `AI_PROVIDER=ollama` remains available for a fully local Qwen deployment. Backend applies the typed evidence-linked graph and trait proposals in its `modeling` stage. See [apps/ios/README.md](../../apps/ios/README.md).

This directory contains schema-validated memory extraction and an evidence-limited Twin worker. `POST /twin` receives only Backend-selected memory snippets and a reviewed question, returns `ORIGINAL`, `SIMULATION`, or `UNKNOWN`, and records the actual DeepSeek response model. Backend alone verifies IDs, exact original spans, Subject authorization, consent, and answer storage.
The iOS-first calibration slice adds `POST /calibrate` for a locked Twin answer and a later confirmed human transcript. The DeepSeek worker returns five typed dimension comparisons; every claimed human excerpt must occur literally in the supplied transcript. Backend owns authorization, chronology, and persistence. Full unattended Capture Planner remains later work.

Phase 1 scope: the Episode/Transcript → Memory Extractor schema, structured output that is validated before persistence, preserved provenance fields, and a minimum AI processing interface callable by Backend with deterministic fixtures.

Inputs and outputs must conform to `packages/contracts`.

Persona proposals now enforce direct-source attribution as well as verified spans: paraphrases remain `AI_INFERENCE`, third-party evidence cannot be relabelled as a Subject quote, and the same evidence cannot both support and contradict a trait. Duplicate trait/fact IDs are rejected before persistence. These checks enforce provenance consistency; semantic support still needs model evaluation. See the [iOS Core verification](../../docs/verification/IOS_AGENT_CORE_2026_10_08.md).

## Local verification

From this directory:

```powershell
uv run pytest -q
```

The checked-in fixtures under `fixtures/` are input-only, deterministic, and
contain no provider credentials or expected provider output.

Version `0.2.0` hardens the Phase 1 implementation. See the
[review and verification record](../../docs/team/02_KANGXIN_AI_CORE_V2_REVIEW.md)
for reproduced defects, fixes, and remaining integration requirements.

## HTTP boundary

Run the service locally with the deterministic provider:

```powershell
$env:REMEMBER_ENVIRONMENT = "development"
$env:AI_PROVIDER = "fixture"
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8100 --log-config app/logging.json
```

The service exposes:

- `GET /health` for provider-neutral liveness;
- `POST /process` accepting the frozen `AICoreInput` and returning only
  `AICoreOutput`.

For a real OpenAI-compatible endpoint, set `AI_PROVIDER=openai_compatible`,
`AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`, and the version settings. Provider
secrets stay in the AI Core process environment and are never returned in an
error body. The fixture provider is refused in `staging` and `production`.
The OpenAI-compatible adapter requires explicit non-fixture `AI_MODEL` and `AI_MODEL_VERSION`; Ollama requires `AI_MODEL` and reads the actual digest itself. For DeepSeek, set `AI_PROVIDER=deepseek`, `AI_MODEL=deepseek-v4-flash`, `AI_BASE_URL=https://api.deepseek.com`, and `AI_API_KEY` in the AI Core process environment. Keep the key outside the repository. The adapter uses JSON output with thinking disabled and records the model identifier returned by DeepSeek (`deepseek-flash` in the verified response). The credential is accepted only for the official HTTPS host.
The active prompt is `memory-extractor-v3`; newly extracted memories use
`integration-contract-v0.2`. Remove an old `AI_PROMPT_VERSION` override or
set it to the current version. Unsupported prompt/schema versions fail startup.

Invalid input returns `422`; provider unavailability returns `503`; provider
timeouts return `504`; invalid structured output or provenance returns `502`.
The response contains stable `error_code` values and safe messages only.
An oversized HTTP request returns `413` with a safe `detail` message. A provider
`429` or local extraction saturation maps to `503 / AI_UNAVAILABLE`; upstream
`408`/`504` map to `504 / AI_TIMEOUT`. Retries belong to Backend; AI Core never
silently retries a paid request. Refusals, unfinished completions and oversized
provider responses are rejected with `502 / AI_SCHEMA_INVALID`.

## Evidence and extraction behavior

- Phase 1 resolves evidence only from the current transcript: both offsets,
  exact non-whitespace excerpt and current Episode reference are mandatory.
  There is no resolver for external evidence or `subject_context` yet.
- Offsets count Unicode code points, with an exclusive end. Android/JavaScript
  UTF-16 indices require conversion, especially for emoji.
- A direct-source Memory must quote an evidence excerpt and keep its source
  label; paraphrases use `AI_INFERENCE`. This validates attribution consistency,
  **not speaker identity or semantic truth**.
- Model/prompt/schema versions are stamped by the service, not trusted from
  model output. Whitespace input returns an empty result without a provider call.
- The real provider receives only `episode_id` and `transcript`. `subject_id`,
  `trace_id`, `subject_context` and prior model state stay local in Phase 1.
- The OpenAI-compatible adapter retains a strict closed-object Phase 1 projection.
  The Ollama and DeepSeek adapters request a compact quote-first shape, then construct v0.2
  Memory, graph, trait, and Evidence records only after locating original spans.
- The offline fixture simulator now extracts multiple clear sentences, deduplicates
  exact repeats, preserves negation, and skips a small set of uncertainty/instruction
  markers per sentence. It is not a production classifier or a security detector.

## Runtime limits and deployment

| Setting | Default | Meaning |
| --- | --- | --- |
| `AI_TIMEOUT_SECONDS` | `30` | HTTP connect/read/write/pool timeout; not a whole-job deadline |
| `AI_MAX_CONCURRENT_REQUESTS` | `4` | Active extractions **per process**; saturation returns 503 |
| `AI_MAX_REQUEST_BYTES` | `1048576` | Maximum raw JSON body, including chunked bodies |
| `AI_MAX_RESPONSE_BYTES` | `1048576` | Maximum decoded provider response bytes |

Synchronous extraction runs in FastAPI's thread pool, keeping `/health` responsive.
Owned HTTP clients close on application shutdown. The supplied logging config
records JSON `trace_id`, outcome and duration, without transcripts or model payloads;
production must route this logger at INFO to retain those events.

This service is an internal Backend dependency. It does not implement Actor/Subject
authorization or a service-auth handshake. Bind to loopback or restrict ingress to
Backend through a private authenticated network/proxy; do not expose this port to
Android or the public internet. Backend must validate Consent and ownership before
calling it. Multi-process/global quotas, HTTP slow-client limits and job deadlines
remain deployment/Backend responsibilities.

## Build and handoff checks

```powershell
uv sync --locked
uv run --locked pytest -q
uv build --wheel
uv run --locked python scripts/check_wheel.py
```

The wheel smoke check extracts the package into a temporary directory and exercises
packaged fixtures and HTTP endpoints without importing source-checkout code.
AI Core CI runs tests and this packaging check on Python 3.12/3.13 when the workflow
is pushed; local validation does not imply that remote CI has already run.

## Backend handoff

Backend owns Episode persistence, retries, processing status, and user-facing
failure state. It should call `POST /process` with `episode_id`, `subject_id`,
`transcript`, `existing_model_version`, and optional `trace_id`. AI Core never
creates or mutates `episode_id` and never writes a database. See
`docs/team/02_KANGXIN_AI_CORE_HANDOFF.md` for the complete handoff checklist.

## 完整循环的反思 worker

Backend 可以在既有 `subject_context` 中发送当前 Subject 的有效画像与校准问题。支持结构化 worker 的供应商在提取后调用 `portrait-reflection-v1`，生成有新证据的 ADD/SUPPORT/CONFLICT/CHANGE 提议及精确引用的记忆侧面。历史目标来自 Backend 快照，程序校验目标、领域、语境和来源；失败返回既有错误，由持久化 worker 重试。AI Core 不直接写画像或数据库。旧调用/fixture 未发送快照时维持原提取路径。

DeepSeek、Ollama 和通用结构化供应商保持同一适配边界；完整 live 验收选择已有 DeepSeek Twin/Calibration worker。供给方能力不一致时保留明确失败，不在客户端替代生成假回答。服务端内部约定、完整循环验收和真实模型质量边界见 [完整记录](../../docs/verification/IOS_FULL_AGENT_LOOP_2026_10_08.md)。公开 Contract 文件与服务 endpoints 均未升级。
