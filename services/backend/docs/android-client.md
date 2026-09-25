# Pointing the Android client at a Backend

Audience: whoever runs the Android app against a real Backend process — the Android module owner on Issue #7, and the Product / Integration Owner running the device gate. This is the operator's view of the API; the payload shapes belong to the contract and are documented in [docs/api/CONTRACT_V0.1.md](../../../docs/api/CONTRACT_V0.1.md), and the endpoint list is in the [module README](../README.md).

Everything here was run on 2026-09-25 against the code in this repository. What was **not** run is stated at the end rather than implied.

## Start the three things

An Episode is created by the API and processed by the worker; they are separate processes (ADR-0001 D2), and the audio is written to the object store the API is configured with. Start the API, the worker, and the seed:

```bash
cd services/backend
export REMEMBER_DATABASE_URL="sqlite:///./var/android-dev/remember-me.db"
export REMEMBER_OBJECT_STORE_ROOT="./var/android-dev/object-store"

mkdir -p var/android-dev
uv sync
uv run alembic upgrade head
uv run python -m app.seed --subject-name "Android Subject" --actor-name "Android Actor"

# One shell: the API, on every interface so a device can reach it.
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Another shell, same two exports: the worker.
uv run python -m app.worker
```

`app.seed` prints four things and they are the only credentials the app needs:

```
subject_id : subj_be57d63ff337419e
actor_id   : actor_b8c9cd8b740749be
consent_id : consent_a290d47d2f94472c
actor token: <printed here, once>
```

The token is the app's own identity, not a provider secret: it is what attributes the recording to an Actor, and it is the minimum Phase 1 authentication rather than production authentication. Provider credentials never leave the server, and the app holds no database or object-storage credential (ADR-0001 D10).

`--host 0.0.0.0` matters. The default binds loopback only, and a device is not the loopback interface.

## Which address the app uses

| Where the app runs | Base URL | Why |
| --- | --- | --- |
| Android emulator | `http://10.0.2.2:8000` | The emulator's alias for the host machine's loopback |
| Physical device, over USB | `http://127.0.0.1:8000` **with** `adb reverse tcp:8000 tcp:8000` | The device's own loopback is forwarded up the adb connection; no Wi-Fi or LAN config |
| Physical device, over Wi-Fi | `http://<host-lan-ip>:8000` | Needs the host to be on the same network as the device |

The first two are the ones to prefer, because they do not depend on the host's network mode.

One honest caveat about running the Backend inside WSL2, which is how this checkout is set up: the process binds a **NAT address** (`172.23.x.x`), and a phone on the Wi-Fi cannot route to it. The Wi-Fi row only works when the host forwards the port (`netsh interface portproxy`) or runs WSL in mirrored networking mode. `adb reverse` avoids the question entirely and is what the device gate should use.

Verified: the API answers on `127.0.0.1:8000` and on its non-loopback address, `/health` and `/ready` both `200`, and the full capture-to-result chain below was run over the non-loopback address. Not verified: a real phone reaching it, because no device is attached to this checkout.

## The three calls, in order

`X-Request-ID` comes back on every response. The same value is the contract's `trace_id`, and it is what makes a client-reported failure findable in the Backend's logs — see [Troubleshooting](#troubleshooting).

**1. Resolve the token** (optional, but it is the cheapest way to prove the app and the service agree):

```bash
curl -s localhost:8000/api/v1/session -H "Authorization: Bearer $TOKEN"
# {"actor_id":"actor_…","display_name":"Android Actor"}
```

**2. Capture.** One multipart request. The audio is the body part named `file`, and its declared content type must be `audio/*`:

```bash
curl -s -X POST localhost:8000/api/v1/episodes \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@take-0001.m4a;type=audio/mp4' \
  -F subject_id="$SUBJECT" \
  -F recording_consent_id="$CONSENT" \
  -F source=ANDROID_MIC \
  -F recorded_at=2026-09-25T09:05:00+08:00 \
  -F audio_ref=take-0001.m4a \
  -F idempotency_key=android-dev-0001
# 201 {"episode_id":"ep_…","upload_status":"uploaded"}
```

| Field | Required | Notes |
| --- | --- | --- |
| `file` | yes | The audio bytes. Content type must start with `audio/` |
| `subject_id` | yes | Who the recording is about |
| `recording_consent_id` | yes | Must be an active `RECORDING` consent **granted by this Actor** for this subject |
| `source` | yes | One of `ANDROID_MIC`, `WORK_3200`, `RECORDING_DEVICE`, `IMPORT` |
| `recorded_at` | yes | ISO 8601 **with an offset**; a naive timestamp is refused |
| `audio_ref` | yes | What the client calls this recording. Recorded as provenance; never dereferenced server-side |
| `idempotency_key` | yes | Stable across retries of the same capture — see below |
| `actor_id` | no | If sent, it must name the authenticated Actor, or the request is refused |
| `duration_ms`, `metadata` | no | `metadata` is a JSON string, because multipart carries no nested objects |

**3. Status, then result.** Status is polled; the result is only served once the Episode is `ready`.

```bash
curl -s localhost:8000/api/v1/episodes/$EPISODE -H "Authorization: Bearer $TOKEN"
# {"episode_id":"ep_…","status":"transcribing"|"extracting"|"modeling"|"ready"|"failed","trace_id":"…"}

curl -s localhost:8000/api/v1/episodes/$EPISODE/result -H "Authorization: Bearer $TOKEN"
# {"episode_id":"ep_…","status":"ready","model_version":"…","memory_items":[…],"trace_id":"…"}
```

Ask for the result before `ready` and it is `409 EPISODE_NOT_READY`, which is distinguishable from `404 EPISODE_NOT_FOUND`. Poll the status endpoint rather than the result endpoint, or treat `409` as "keep waiting" rather than as an error.

The status values are the contract's `processingStatus` enum and each one names the stage the worker is on. They advance one stage at a time, and each stage is committed on its own, so a poll during a slow provider call sees where the work is rather than waiting for the whole pipeline. With the fake providers each stage takes milliseconds, so a poll usually only ever sees `ready`.

## Limits and failure behaviour

| Limit | Value | Refusal |
| --- | --- | --- |
| Largest upload | 25 MiB (`REMEMBER_MAX_UPLOAD_BYTES`) | `413 AUDIO_TOO_LARGE` |
| Content type | must start with `audio/` | `400 AUDIO_INVALID` |
| Empty upload | — | `400 AUDIO_INVALID` |
| Same key, different audio | — | `409 IDEMPOTENCY_CONFLICT` |

A reverse proxy in front of the API needs a body limit at least as large as `REMEMBER_MAX_UPLOAD_BYTES`, or the request is refused before the service sees it.

**Retry the same capture with the same `idempotency_key`.** Replaying returns the Episode the first request created, with `200` instead of `201` and the same `episode_id` — no second Episode, no second audio object, no re-running STT or AI. This is what makes a retry safe after a dropped connection, and it is why the key must be stable across retries of one recording rather than regenerated: a new key with the same audio creates a second Episode. Uniqueness is scoped to `(subject_id, actor_id, idempotency_key)`, so two Actors using the same key do not collide.

The upload is a normal request and can fail like one (`503 STORAGE_UNAVAILABLE` if object storage refuses). Processing is different: it happens **after** the Episode is committed, so a processing failure is recorded **on the Episode** as `error_code` and `error_message` and the Episode stays readable. A model outage never loses the recording (ADR-0001 D11), and a failed Episode is retryable with the same key.

## Troubleshooting

The client's identifier is the `episode_id`; the log identifier is the `trace_id`; the status endpoint is what converts one into the other.

| Symptom | What it means | What to do |
| --- | --- | --- |
| Connection refused | The API is not running, or is bound to loopback only | Start it with `--host 0.0.0.0`; check `curl <base-url>/health` from the host |
| `401 AUTH_REQUIRED` / `AUTH_INVALID` | No token, or a token this database does not know | Re-run `app.seed`, or point the app at the database that seeded it |
| `404 SUBJECT_NOT_FOUND` | The `subject_id` is not in the database the API is using | Re-seed, or fix the app's ids to match that database |
| `404 CONSENT_NOT_FOUND` | The consent id is unknown **to this Actor** — a wrong id and another Actor's grant answer identically | Use the `consent_id` `app.seed` printed for this Actor |
| `403 CONSENT_INVALID` | The consent is this Actor's but revoked, for another subject, or of another scope | Grant a fresh `RECORDING` consent for the subject via `POST /api/v1/consents` |
| `400 AUDIO_INVALID` | The part is empty, or its content type is not `audio/*` | Declare the type on the file part; a `.m4a` whose type is guessed as `application/octet-stream` is refused |
| `413 AUDIO_TOO_LARGE` | Over 25 MiB | Raise `REMEMBER_MAX_UPLOAD_BYTES`, and the proxy's limit with it |
| Episode stays `uploaded` and never moves | The worker is not running, or not pointed at the same database and object store | Start `uv run python -m app.worker` with the same two exports as the API |
| `404 EPISODE_NOT_FOUND` | The Episode is unknown **to this Actor** | The capturing Actor's token is the only one that can read it (ADR-0001 D7) |
| `409 EPISODE_NOT_READY` | Asked for the result too early | Keep polling the status endpoint |

To see what the worker actually did, take the `trace_id` the status endpoint returned and grep both logs for it:

```bash
grep "$TRACE_ID" api.log worker.log
```

Both processes write one JSON object per line with the same `trace_id`, so the request that created the Episode, each stage the worker completed with its duration and provider, and any stage failure are one grep apart. No log line carries the actor token or the transcript; a transcript is the subject's speech and a log line is written to disk.

## What this environment is, and is not

**It is** the wiring environment: a real API, a real worker, a real database, real object storage, and a real device recording flowing through the real contract. Upload, idempotency, status transitions, the result shape, the consent and Actor checks, and the error codes are all exercised.

**It is not** proof of recognition. `development` and `test` are the only environments where the fake providers may run, and they are the default — so the transcript here reads `[fake-stt] …` and the Memory reads `[fake-ai] …`, both labelled as placeholders on purpose. No real speech recognition has run, and a record from this environment cannot support the Phase 1 acceptance, which needs a real STT provider and a consented device recording (`issue #64` is where the endpoint is being certified). The Backend side of that is ready — `REMEMBER_STT_BACKEND=http` selects the real transport, and switching it is configuration rather than code — but no certified endpoint is configured in this checkout, so **the real-chain run is blocked, not pending work in this module**.