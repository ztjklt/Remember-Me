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

The audio file stays in the app's Documents/Recordings directory even after an
upload or processing failure. On restart the most recent saved recording and
Episode ID can be recovered. The upload uses `source=IMPORT` because Contract
v0.1.2 has no iOS microphone enum; the app first saves a local file and then
imports it. A versioned Contract proposal is needed before adding `IOS_MIC`.

This client does not itself certify Phase 1 or the later phase gates. A real
device, real STT, a working AI provider, persisted Memory, and an acceptance
record are needed for the former. Phase 2–4 endpoints and providers remain
separate planned work on this branch.
