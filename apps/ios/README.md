# Remember Me iOS branch

This is an independently developed iOS client on the `ios` branch. The existing
Backend, AI Core and frozen Phase 1 Contract are reused; Android remains the
team's product baseline on `develop`. No iOS provider credentials are bundled.

## Build

Requires Xcode 27 and XcodeGen 2.46 or newer. The generated Xcode project is
committed so XcodeGen is not required just to open the app.

```bash
cd apps/ios
xcodegen generate
xcodebuild -project RememberMeIOS.xcodeproj -scheme RememberMeIOS \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro,OS=26.5' build test
```

## Run the local Phase 1 path

1. Start Backend API and worker from `services/backend/README.md` and apply its
   migrations. For local sign-in use the development mail inbox in
   `services/backend/var/dev-mailbox/`; configure SMTP for delivered email.
2. Configure Backend with an HTTP STT service and AI Core with a real model to
   test the true path. Fake providers are useful only for wiring checks.
3. In the simulator, set Backend URL to `http://127.0.0.1:8000`; on a phone,
   use a reachable private-network hostname or HTTPS endpoint. Sign in with an
   email code, then explicitly approve recording and upload. Access and refresh
   tokens are stored in the iOS Keychain; the new account owns its own Subject.
   For a local development iPhone, a one-time `Documents/rememberme-local-connection.json`
   with `baseURL`, `token`, `subjectID`, `email`, and `refreshToken` can be copied
   into the app data container before launch. Debug builds import it into
   Settings and Keychain, then delete the plaintext file after successful
   import. Release builds ignore this file. It never carries provider secrets.
4. Stop a recording to save and automatically upload it. The left-hand capture
   bubble first confirms local receipt, then displays the actual STT transcript
   and extracted Memory for that Episode. Failed uploads retain the local file;
   failed processing can be retried from the same Episode.

For a recording device that exports files, use **从文件导入设备录音**. The app copies
`.m4a` or `.wav` into its own recordings folder, checks the 25 MiB limit, lets
the user correct the capture time, and uploads through the existing `IMPORT`
path. This is a hardware-free fallback; it does not claim Work 3200 SDK support
or markers. The selected capture time persists across app restarts.

For a repeatable local service check after starting the real STT bridge on
`127.0.0.1:8200` and AI Core on `127.0.0.1:8100`, run:

```bash
cd services/backend
PHASE1_AUDIO_PATH=/absolute/path/to/consented-recording.m4a \
  uv run --locked python ../../scripts/verify_ios_local_stack.py
```

Set `IOS_VERIFY_EXTENDED=1` on the same command to continue after Phase 1 with
the real-provider Persona synthesis and temporal graph, Twin Agent,
real-model calibration comparison, Capture Planner, and recipient grant/revoke
checks. The wrapper creates disposable Actor tokens and a temporary database.
The extended result remains a service check, not a real-device, clone-voice,
hardware, or formal Legacy acceptance result.

The script applies Backend migrations to a temporary SQLite database, seeds a
private Actor token, starts the API and worker, uploads with `source=IMPORT`,
and verifies that real STT and non-fixture AI produced persisted Memory and
Evidence for the same Episode. Its synthetic-audio run is a technical check;
real device acceptance needs a recording from the app.

The audio file stays in the app's Documents/Recordings directory even after an
upload or processing failure. On restart the most recent saved recording and
Episode ID can be recovered. The upload uses `source=IMPORT` because Contract
v0.1.2 has no iOS microphone enum; the app first saves a local file and then
imports it. A versioned Contract proposal is needed before adding `IOS_MIC`.

The Memories tab reads Actor-owned ready Episodes with evidence. With a real
AI Core provider, the worker calls Persona to synthesize versioned seven-domain
traits, temporal validity, conflict state, entities and relationships. Each
trait and graph link must cite a current Memory. The graph also preserves
Episode and Evidence provenance. Corrections, deletions and consent changes
invalidate derived traits in the same transaction; a subsequent read or Twin
query rebuilds them. During provider failure, the model reports `rebuilding`
and Twin cannot use stale traits. A Persona failure after successful extraction
does not discard the Episode transcript or Memory; the derived model remains
queued for a later rebuild. The Twin Agent searches current evidence
semantically, returns one exact Subject excerpt as ORIGINAL when it answers the
question, otherwise returns a cited SIMULATION or refuses. The Backend verifies
citations and keeps the shared Contract unchanged. Fixture mode remains an
explicit deterministic test path. Semantic quality still needs human evaluation
on real recordings.

The Memories tab can now submit an Actor correction proposal for a Memory.
Corrected items remain visible with the original evidence, but Twin immediately
stops using the disputed claim until the proposal is withdrawn or a future
verified reprocessing path resolves it. Deleting a Memory removes the derived
item from Episode results, the cross-Episode list and Twin retrieval. Its source
Episode, transcript and raw Evidence remain for provenance; this operation is
not an Episode or account erasure request.

The Calibration screen persists a locked Twin answer and its evidence IDs under
the Actor's active `CLOUD_TWIN` consent before accepting a human answer and
manual gap marks for decision, reasoning, value priority, emotional reaction,
and expression. An optional AI comparison then assesses those two fixed answers
across the same five dimensions. The assessment is model-versioned, immutable,
Actor-isolated, and marked uncertain where both answers lack direct information.
Only an account bound to its own Subject can explicitly confirm the result.
Confirmed feedback is stored as provisional calibration input and can affect
the next guided question; it is kept separate from source-grounded facts.

Twin answers also have an iOS system-speech fallback. Each playback asks
Backend to authorize an active, separate `VOICE` consent and stops when the app
goes to the background. The button explicitly says this is **not** the Subject's
cloned voice. No Voice dataset, speaker verification, clone provider or profile
is created by this fallback.

On a supported device, the user may also explicitly authorize access to an
[Apple Personal Voice](https://developer.apple.com/documentation/avfaudio/avspeechsynthesizer/requestpersonalvoiceauthorization%28completionhandler%3A%29)
that they already created in iOS Accessibility settings. The app offers it only
after system authorization and explicit selection of a voice; it still checks Backend `VOICE` consent on each
playback. This is on-device playback, not a Voice profile built from Remember Me
Episodes. The current account model cannot verify that the device's Personal
Voice belongs to the selected Subject, so the UI labels that limitation.

Capture offers two to four model-planned Chinese questions with one or two
follow-ups each. The real Capture Planner uses seven-domain coverage, current
traits, contradictions and confirmed calibration answers. Its priority factors
are estimates, not measured information gain. Fixture mode keeps a documented
heuristic for offline tests. Questions update after new Episodes or confirmed
calibration feedback.

The Handover tab provides a manual Legacy **preview**: the capturing Actor must
grant separate `DIGITAL_HANDOVER` consent, name an existing Recipient Actor, and
choose visible Memory domains. A draft exposes nothing. Explicit preview
activation freezes the eligible Memory IDs; later captures do not enter that
snapshot. Corrected or deleted items disappear from recipient retrieval, and
grant or consent revocation cuts access immediately. The Recipient signs in with
their own Actor token and reads the preview from the same tab. Activation also
records the Person Model revision, and the grantor can inspect append-only
create, activate, recipient read, and revoke events. There is no
formal Legacy activation, death verification, identity proof, voice grant, or
legal authority check in this branch.

The local service check on 2026-09-25 passed real Whisper STT, DeepSeek
extraction, persistence, evidence-labelled Twin, calibration comparison and
revocable handover preview using a synthesized audio file. It did not exercise
iPhone capture. A real device, a complete capture to display run and an
acceptance record are still needed. Phase 2 still needs evaluated semantic links,
verified correction promotion, and a semantically evaluated Twin. Phase 3 still needs
verified Subject feedback, empirical calibration evaluation, and real Voice. Phase 4 still needs
formal activation and verified hardware integration.
