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

1. Start Backend API and worker from `services/backend/README.md`, apply its
   migrations, and seed an Actor and Subject. Keep the generated token private.
2. Configure Backend with an HTTP STT service and AI Core with a real model to
   test the true path. Fake providers are useful only for wiring checks.
3. In the simulator, set Backend URL to `http://127.0.0.1:8000`; on a phone,
   use a reachable private-network hostname or HTTPS endpoint. Enter the seed
   Actor token and Subject ID. The token is stored in the iOS Keychain.
4. Tap **我确认并登记录音同意**. This creates a RECORDING consent for that Actor and
   Subject. It does not grant VOICE consent.
5. Record, pause/resume, save, play, upload, and observe the Episode state and
   returned Memory. The same `episode_id` is retained for retries and refreshes.

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

The iOS branch also has a provisional Phase 2 read path. Its Memories tab reads
all Actor-owned, ready Episodes and shows evidence and conservative domain clue
counts (unclassified items stay unclassified). The Backend's model stage now
materializes an Actor-partitioned, versioned Person Model preview from these
provenance-linked items. Corrections and deletions rebuild the preview and bump
its revision; the app shows the version, domain coverage and latest source fact.
It does not synthesize unsupported traits or a semantic temporal graph. The
Twin tab requires a separate `CLOUD_TWIN` consent. It returns an ORIGINAL excerpt
only for a conservative direct Subject match. Related AI-inferred excerpts are
shown as SIMULATION with explicit speaker uncertainty and confidence capped at
0.5; unrelated questions return insufficient evidence with zero confidence.
This is a deterministic evidence router, not
a full semantic Person Model or generative Twin. The shared Contract is unchanged.

The Memories tab can now submit an Actor correction proposal for a Memory.
Corrected items remain visible with the original evidence, but Twin immediately
stops using the disputed claim until the proposal is withdrawn or a future
verified reprocessing path resolves it. Deleting a Memory removes the derived
item from Episode results, the cross-Episode list and Twin retrieval. Its source
Episode, transcript and raw Evidence remain for provenance; this operation is
not an Episode or account erasure request.

The Calibration tab starts by persisting a locked Twin answer and its evidence
IDs under the Actor's active `CLOUD_TWIN` consent. Only after that does it
accept a human answer and manual gap marks for decision, reasoning, value
priority, emotional reaction, and expression. Completed records are immutable
and Actor-isolated. This is a Phase 3 calibration capture loop; it does not yet
verify that the Actor is the Subject, automatically compare the answers, or
update the Person Model.

Twin answers also have an iOS system-speech fallback. Each playback asks
Backend to authorize an active, separate `VOICE` consent and stops when the app
goes to the background. The button explicitly says this is **not** the Subject's
cloned voice. No Voice dataset, speaker verification, clone provider or profile
is created by this fallback.

Capture offers a guided preview of up to four questions. Backend ranks seven
fixed-domain prompts by a documented heuristic score based on estimated
information gain, importance, uncertainty, recent calibration gaps and
interaction cost. The questions update after new Episodes or calibration
feedback. This is not an automatic interviewing agent or an empirical measure
of information gain.

The Handover tab provides a manual Legacy **preview**: the capturing Actor must
grant separate `DIGITAL_HANDOVER` consent, name an existing Recipient Actor, and
choose visible Memory domains. A draft exposes nothing. Explicit preview
activation freezes the eligible Memory IDs; later captures do not enter that
snapshot. Corrected or deleted items disappear from recipient retrieval, and
grant or consent revocation cuts access immediately. The Recipient signs in with
their own Actor token and reads the preview from the same tab. There is no
formal Legacy activation, death verification, identity proof, voice grant, or
legal authority check in this branch.

This client does not itself certify Phase 1 or the later phase gates. A real
device, real STT, a working AI provider, persisted Memory, and an acceptance
record are needed for Phase 1. Phase 2 still needs a semantic temporal graph,
verified correction promotion, and a semantically evaluated Twin. Phase 3 still needs
automatic comparison, Capture Planner and real Voice. Phase 4 still needs
formal activation and verified hardware integration.
