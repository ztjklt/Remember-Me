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
counts (unclassified items stay unclassified). The
Twin tab requires a separate `CLOUD_TWIN` consent. It returns an ORIGINAL excerpt
only for a conservative direct match; otherwise it reports insufficient evidence
as SIMULATION with zero confidence. This is a deterministic evidence router, not
a full semantic Person Model or generative Twin. The shared Contract is unchanged.

The Memories tab can now submit an Actor correction proposal for a Memory.
Corrected items remain visible with the original evidence, but Twin immediately
stops using the disputed claim until the proposal is withdrawn or a future
verified reprocessing path resolves it. Deleting a Memory removes the derived
item from Episode results, the cross-Episode list and Twin retrieval. Its source
Episode, transcript and raw Evidence remain for provenance; this operation is
not an Episode or account erasure request.

This client does not itself certify Phase 1 or the later phase gates. A real
device, real STT, a working AI provider, persisted Memory, and an acceptance
record are needed for Phase 1. Phase 2 still needs a temporal graph, verified
correction promotion, and a semantically evaluated Twin. Phase 3–4 endpoints
and providers remain separate work on this branch.
