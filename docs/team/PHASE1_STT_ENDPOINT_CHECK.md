# Phase 1 STT endpoint handoff

Owner: Product / Integration (`@ztjklt`), Issue #64. Backend/STT module Owner
remains `@qingtian-4` under Issue #57. This check certifies a candidate
endpoint against the HTTP wire already used by Backend; it does not change
Backend code, select a vendor, or pass the real-device Phase 1 gate.

## Configure and run

The service or a server-side gateway must accept the raw audio body at
`POST {REMEMBER_STT_URL}{REMEMBER_STT_PATH}` with the audio MIME type as
`Content-Type`. It must answer HTTP 200 with JSON `text` and `model_version`.
The Backend adapter can store an unreported version, but this acceptance check
requires a reported non-fake version so the real STT run is traceable.

Supply these values through the local environment or secret manager; keep
provider credentials in the STT service or gateway, not Android or Backend:

| Variable | Meaning |
| --- | --- |
| `REMEMBER_STT_URL` | Reachable HTTP(S) base URL, without credentials |
| `REMEMBER_STT_PATH` | Absolute path, for example `/transcribe` |
| `REMEMBER_STT_TIMEOUT_SECONDS` | Optional positive finite timeout; default 60 |
| `PHASE1_AUDIO_PATH` | A consented real recording of at most 25 MiB |
| `PHASE1_EXPECTED_TEXT_FRAGMENT` | Optional phrase known to be spoken, for a recognition spot check |

```bash
cd services/backend
uv run --locked python ../../scripts/test_verify_stt_endpoint.py
uv run --locked python ../../scripts/verify_stt_endpoint.py
```

The command sends the exact raw bytes and MIME type that Backend's
`HttpSttProvider` sends. It rejects non-200 responses, malformed JSON, empty
or fake transcripts, missing or fake model versions, timeouts, and a missing
expected phrase. It prints byte count, transcript character count, model
version, elapsed time, and whether the optional phrase matched. It never
prints the transcript, the phrase, provider response body, or credentials.

The seven deterministic tests use an in-process HTTP transport. They prove
wire compatibility and safe failures, not real speech recognition. To hand
the endpoint to Backend, record the service revision, the safe command output,
the audio provenance and consent, and any first failing hop in Issue #64.
Then @qingtian-4 configures `REMEMBER_STT_BACKEND=http` with this same URL and
path, runs the worker, and checks the persisted Episode and Memory through
the Phase 1 integration runbook. Only a physical Android recording, real STT,
real AI extraction, and Android rendering the same Episode can close #21.
