# Remember Me reusable components

Remember Me reuses mature engines behind existing adapters and adopts design patterns where another product's storage, consent or client model does not fit. The current slice adds a real optional STT engine, improves evidence handling and interview questions, strengthens numerical voice QA, and prepares Graphiti and Legacy boundaries. Existing hardware work is reused through its owner branch. Existing public schemas remain unchanged.

## Component decisions

| Source | Adopted part | Implementation and readiness |
| --- | --- | --- |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Local transcription and built-in Silero VAD | `services/backend/app/faster_stt.py`; callable through the existing STT sidecar, opt-in only |
| [Omi](https://github.com/BasedHardware/omi) | Capture, transcription, memory and device capabilities as separate concerns | Preserve the existing Episode-first pipeline; add bounded STT inference and reuse Android capability selection in PR 61. No Flutter/Firebase stack is copied |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal graph as a derived retrieval projection | `services/backend/app/graph_projection.py`; adapter preparation tested against SDK 0.30.2 signatures, not wired to APIs or a running graph database |
| [OpenSelf](https://github.com/Open-Self/Open-Self) | Source attribution, scoped retrieval, context freshness | Recheck recording/cloud authority and the Person Model revision before saving Twin output; never relabel an old context with a new revision. Keep current Backend storage |
| [Digital Replicant](https://github.com/bobbjedi/replicant) | Experience-first interviews covering motivation and context | Existing seven-domain questions now request concrete experiences; conflict follow-up asks about differing contexts and keeps both evidence sets |
| [Second Me](https://github.com/mindverse/Second-Me) | Separate episodic records, person understanding and expression | Reuse Remember Me's existing Episode/Memory/Person Model/Twin layers. Personal model training is not required for this slice; correction and provenance remain explicit |

Omi, OpenSelf, Replicant and Second Me are design references here; their source code and runtime dependencies are not vendored. Faster-whisper is installed as an optional dependency. Its upstream license is MIT. Graphiti's upstream license is Apache 2.0; no Graphiti source is copied into the repository. Pin a deployment's Graphiti SDK before integrating the prepared adapter.

## Phase 1 transcription

The existing `/transcribe` wire remains raw audio in and JSON `text` plus `model_version` out. `whisper_cpp` remains the default. The optional engine is `faster_whisper`.

```bash
cd services/backend
uv sync --locked --extra local-stt
export REMEMBER_LOCAL_STT_ENGINE=faster_whisper
export REMEMBER_FASTER_WHISPER_MODEL_PATH=/absolute/path/to/multilingual-ctranslate2-model
export REMEMBER_LOCAL_STT_DEVICE=cpu
export REMEMBER_LOCAL_STT_COMPUTE_TYPE=int8
uv run --locked --extra local-stt uvicorn app.local_stt:app --host 127.0.0.1 --port 8200
```

Download weights explicitly before starting. An example smoke-test snapshot is `Systran/faster-whisper-tiny` at revision `d90ca5fe260221311c53c58e660288d3deb8d356`; tiny is a probe model, not a claim that Chinese product-quality acceptance has passed. Model accuracy and the final STT choice require representative recordings.

The optional extra pins faster-whisper 1.2.1 and PyAV 16.1.0. A real probe found that PyAV 19 removed an argument used by this faster-whisper release; the tested pin prevents that failure. Audio is decoded locally. Requests do not download weights. Fingerprints include weights, tokenizer/config, library version and selected inference options and fit the existing 64-character STT version column.

The sidecar holds one inference slot per process, including generator consumption. Busy requests return 503 for the existing Worker retry budget. CLI subprocess timeouts return 504. Empty, oversized or non-audio requests fail before inference. Silence may return empty text; Backend retains its existing `STT_EMPTY_TRANSCRIPT` failure. STT and VAD do not identify the speaker.

## Phase 2 graph and context

The Graphiti adapter accepts only scoped, evidence-linked Memory projections with time, confidence and model/prompt/schema versions. Configure a Graphiti client with explicit graph, LLM, embedding and reranking providers, then pass it and `EpisodeType.json` to `GraphitiProjection`; no provider defaults are instantiated by this adapter.

Index groups and deterministic UUIDs include both Subject and committed model revision. Search results must belong to that exact group and cite only known projection UUIDs. The adapter returns Memory IDs; Backend must reload their active records and evidence under current authorization. Generated graph statements never become original Subject quotations or replace the seven-domain model.

Correction/deletion switches the readable revision immediately; removal of obsolete projection episodes remains an explicit, observable cleanup step. Revision filtering is not a substitute for deleting sensitive graph data. Full integration requires a durable projection job/outbox, graph deletion verification, provider configuration and consent checks before any data reaches a model. Neither `ProcessingWorker` nor `/memory-search` currently calls this prepared adapter.

Twin saving now verifies that the same revision was used throughout generation and that recording and cloud access remain active. Its conditional revision write fence reuses PR 86's approach, including SQLite compatibility. Correction, deletion or revocation during inference refuses the response rather than publishing an answer to obsolete evidence.

## Phase 3 interviews and voice

Keep Replicant's focus on concrete experiences, motivation and exceptions. Ask a small number of questions and accept that different contexts can support different views. A single response is evidence for a candidate understanding, not a permanent personality label.

[PR 86](https://github.com/ztjklt/Remember-Me/pull/86) already contains the more complete adaptive Capture Planner, temporal reasoning and calibration flow. Reuse that implementation rather than introducing a second scheduler. When integrating PR 86, carry the improved question wording into its `QUESTIONS` bank and retain its burden, cooldown and evidence logic. Its Twin snapshot protection overlaps this slice and should be consolidated on rebase. [PR 87](https://github.com/ztjklt/Remember-Me/pull/87) contains the Android memory core; keep its client assembly independent of these provider changes.

Voice continues to use the existing Qwen3-TTS/MLX adapter under a separate VOICE grant and dedicated own-voice confirmation. Numerical sample QA now rejects excessive clipping and fewer than two seconds at the existing audible-level threshold, as well as existing duration/level failures. The streamed validation body is bounded before decoding.

These checks do not establish speech, number of speakers or identity. Automatic speaker verification and clean-segment selection remain additional work; no similarity threshold or third-party model is silently selected. Unattended/imported speech must not enter the current Voice profile path. The module is tested without loading Qwen/MLX or using anyone's voice.

## Phase 4 hardware and Legacy

[PR 61](https://github.com/ztjklt/Remember-Me/pull/61) already implements `CaptureCapabilityProfile`, `SelectingAudioCaptureService` and phone fallback. Reuse that owner's implementation and port it incrementally to the current recording API rather than creating another capability hierarchy. Device capture must support recording retrieval; pause and playback remain optional. No Work 3200 SDK or real-device capability is established by this slice. Markers and live audio require explicit SDK verification before adding them to that existing profile.

`FrozenBaseline` captures a versioned seven-domain snapshot into immutable canonical bytes and returns detached views. World and Recipient context remain separate. The content fingerprint is neither a consent proof nor a digital signature. The caller must verify prior Subject authorization before activation.

No activation, grant or Recipient endpoint is exposed. The [Legacy contract proposal](../proposals/REUSE_LEGACY_CONTRACT.md) supplies a concrete review boundary before persistence, policy evaluation and client integration. Freezing a value object is not the complete Legacy experience.

## Local verification on 2026 10 09

- Backend and numerical Voice QA: `cd services/backend && uv run --locked --extra local-stt pytest -o addopts='' -q ../voice/tests tests` — 278 passed. Voice verification includes actual FFmpeg decoding of a synthesized WAV without loading a voice model.
- After adopting the conditional revision write fence and adding scoped graph-fact checks to the frozen baseline, targeted verification `uv run --locked --extra local-stt pytest -o addopts='' -q tests/test_twin_voice.py tests/test_legacy_baseline.py` — 14 passed, including three added graph-fact cases.
- Android baseline: JDK 17 and SDK path supplied to `./gradlew test assembleDebug`; unit tests and debug APK build passed. This slice ultimately makes no Android code changes; PR 61 remains the source for capability integration.
- Real optional-engine HTTP probe: macOS Tingting synthesized a Chinese sentence; the tiny model decoded it through `/transcribe`; the existing endpoint verifier reported `expected_phrase=pass` for 家人. Audio was generated for testing, not recorded from a person. This does not satisfy a real-device Phase Gate or verify general recognition accuracy.
- Graphiti 0.30.2: `create_autospec(Graphiti)` exercised the adapter's `add_episode`, `search` and `remove_episode` calls with real SDK signatures; no graph database or LLM was called.
- Public schemas are unchanged; the local STT sidecar adds a liveness-only `/health` endpoint. No migrations, real audio, model weights or provider credentials are committed. Graphiti/Legacy preparation and the hardware integration reference are not an end-to-end product acceptance claim.
