# Local native companion acceptance

These scripts preserve the **2026-10-12 historical A01 acceptance**, not a fresh
clone bootstrap. Start a new empty installation with
[the local setup guide](../../../docs/agent-loop/TWIN_LOCAL_SETUP_2026-10-12.md).
The old subject ID, recording hash, reviewed records and private accounts are not
created or supplied by these scripts. The write runner still requires that exact
existing A01 runtime and `emulator-5554`; do not substitute a new database or WAV
and represent it as the historical run. The read-only runner also expects existing
reviewed content; its role/ID arguments select that content rather than seed it.

Both scripts locate ADB using `ANDROID_HOME/platform-tools`, then
`ANDROID_SDK_ROOT/platform-tools`, then `PATH` (`adb.exe` on Windows). No personal
SDK path is required. This tool lookup does not relax the historical data, device
or explicit execution prerequisites below.

This run makes real local writes and one provider question. Run only after the
coordinator explicitly frees the A01 runtime. It never starts an emulator, creates
new TTS material, resets app data, retries provider work, or contacts ECS.

Prerequisites: existing `emulator-5554`, text scale 1.0, current debug and androidTest
APKs installed with `adb install -r`, backend reachable directly at
`http://10.0.2.2:8891`, and ignored `private/local-accounts.json`. Build with
`assembleDebug assembleDebugAndroidTest`; debug version includes
`-persona-local-20261012`. The internal release configuration is unchanged.

From repository root, run one phase at a time and inspect each result:

```powershell
python apps/android/scripts/persona_companion_live.py reader-create --execute-authorized
python apps/android/scripts/persona_companion_live.py owner-accept --execute-authorized
python apps/android/scripts/persona_companion_live.py reader-opt-in --execute-authorized
python apps/android/scripts/persona_companion_live.py reader-question --execute-authorized
python apps/android/scripts/persona_companion_live.py reader-withdraw --execute-authorized
python apps/android/scripts/persona_companion_live.py owner-verify --execute-authorized
```

Use one explicit `--output` path consistently to isolate a new authorized run.
An existing phase directory refuses execution. If a phase partially succeeds,
inspect its journal before continuing; `--resume-submitted` allows owner acceptance
of the same already-created note, without uploading/transcribing/creating again.
The runner pulls failure evidence before reporting failure. Never rerun create to
recover later steps. A failed question is recorded as `question_error`, with no
automatic second question or synthesis. `completed` denotes the phase ran, not
that a question produced an answer; inspect `answer` and `question_error`.

The WAV is the immutable existing `voice-companion-live-20261012/materials/companion.wav`.
Host and app both check SHA-256. ADB push/copy preserves binary bytes. Instrumentation
calls the same production import action as the picker callback, rather than driving
the Android file picker or simulating a microphone. Other contribution operations
use real Compose controls. The specified question uses the production model action
with persona mode and explicit cloud consent. Login uses the real account endpoint.

ASR review deliberately confirms the actual returned text unchanged for transport
acceptance; this is an automated review action, not a human listening-quality claim.
Inspect the raw/transcript/reviewed texts for recognition or punctuation errors.
Results include actual IDs, revisions, states, error responses and native screenshots.
Credentials are consumed from app-private storage and omitted from evidence.

The 2026-10-12 execution preserved two failures: binary stdin truncated the WAV
before any upload; then author permission on a pending note was rejected. The UI
now disables model-use permission until accepted or kept as a disagreement. The
same submitted note continued through owner acceptance then separate permissions;
no second ASR or contribution was created. The single quote/attribution question
also failed backend answer validation and is not represented as a successful answer.
