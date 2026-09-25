# AI Core Service

Owner: 康欣 (`centraler`). Phase 1 — COMMITTED. See the [task brief](../../docs/team/02_KANGXIN_AI_CORE.md).

This directory contains schema-validated Memory extraction and, on the isolated
`ios` branch, real-provider Persona synthesis, semantic Twin routing, calibration
comparison and guided Capture planning. The domain layer stays provider-neutral;
the HTTP adapter is OpenAI-compatible and does not select a vendor.

Phase 1 scope: the Episode/Transcript → Memory Extractor schema, structured output that is validated before persistence, preserved provenance fields, and a minimum AI processing interface callable by Backend with deterministic fixtures.

Inputs and outputs must conform to `packages/contracts`.

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
- `POST /calibrate` comparing a locked Twin answer with a later human answer.
  It returns a versioned, advisory five-dimension assessment. The fixture
  provider refuses this operation; a configured real provider is required.
- `POST /twin/simulate` selecting at most three relevant evidence IDs from a
  supplied, bounded candidate set. It does not generate an answer. Backend
  validates citations and shows the source excerpts with a simulation caveat.
  The fixture provider refuses this operation.
- `POST /persona/reconcile` synthesizing evidence-cited seven-domain traits,
  temporal conflict states, entities and relations from current Memory sources.
- `POST /twin/answer` retrieving relevant excerpts semantically and returning
  an exact ORIGINAL quote, a cited SIMULATION, or a refusal.
- `POST /capture/plan` proposing two to four Chinese questions with contextual
  follow-ups from current traits, coverage and confirmed calibration gaps.

The three new model endpoints require a real provider. Their closed schemas and
source-ID checks reject invented citations. A bounded regeneration attempt is
used for malformed extraction output; it never relaxes provenance validation.

For a real OpenAI-compatible endpoint, set `AI_PROVIDER=openai_compatible`,
`AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`, and the version settings. Provider
secrets stay in the AI Core process environment and are never returned in an
error body. The fixture provider is refused in `staging` and `production`.
Providers that implement JSON object output but not Chat Completions JSON Schema
can set `AI_STRUCTURED_OUTPUT_MODE=json_object`. AI Core sends the output schema
as prompt guidance and still validates the returned JSON, evidence and versions
before Backend can persist it. The default remains `json_schema`.

For the current DeepSeek Chat Completions API, a local, git-ignored `.env` can
contain `AI_PROVIDER=openai_compatible`, `AI_BASE_URL=https://api.deepseek.com`,
`AI_MODEL=deepseek-flash`, `AI_STRUCTURED_OUTPUT_MODE=json_object`, an explicit
`AI_MODEL_VERSION` deployment label, and `AI_API_KEY`. DeepSeek's JSON object
mode guarantees parseable JSON, not conformity to this project's schema; AI Core
keeps its own validation and may reject an unsupported claim or ambiguous quote.
Backend uses only the AI Core URL and never receives the provider key.
Real providers require explicit non-fixture `AI_MODEL` and `AI_MODEL_VERSION`.
The active prompt is `memory-extractor-v2`; the shared schema remains
`integration-contract-v0.1.2`. Remove an old `AI_PROMPT_VERSION` override or
set it to the current version. Unsupported prompt/schema versions fail startup.

The isolated `ios` branch also supports a local Ollama adapter. Start Ollama
with an installed model, then set `AI_PROVIDER=ollama_local`,
`AI_BASE_URL=http://127.0.0.1:11434`, `AI_MODEL` to that model's name, and
`AI_MODEL_VERSION` to a non-fixture deployment identifier. The adapter uses
Ollama's native structured output with thinking disabled. It can relocate a
model's Chinese evidence excerpt only when a one-to-one Traditional/Simplified
conversion finds a unique match; it then copies the exact original transcript
text into the evidence. Ambiguous or unsupported spans still fail validation.
This is a local provider option, not proof of semantic extraction quality.
For calibration, the provider receives only the question and the two answers.
The service verifies a closed result schema and forces each dimension to
`UNCERTAIN` unless both answers directly mention that dimension. It also
refuses a confident comparison when the locked Twin answer itself says the
evidence is insufficient. The comparison is advisory, not identity proof or
an automatic Person Model update.

Invalid input returns `422`; provider unavailability returns `503`; provider
timeouts return `504`; invalid structured output or provenance returns `502`.
The response contains stable `error_code` values and safe messages only.
An oversized HTTP request returns `413` with a safe `detail` message. A provider
`429` or local extraction saturation maps to `503 / AI_UNAVAILABLE`; upstream
`408`/`504` map to `504 / AI_TIMEOUT`. Transport retries belong to Backend.
The extractor may make one bounded regeneration request after malformed schema
or provenance; persistent invalid output fails closed. Refusals, unfinished
completions and oversized provider responses are rejected with
`502 / AI_SCHEMA_INVALID`.

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
- Strict provider JSON Schema is a closed-object projection; the shared contract
  is unchanged. The model is asked to leave metadata null and future arrays empty.
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
