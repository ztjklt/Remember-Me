# WORK_3200 home capture delivery — 2026-10-16

User approved the home-capture design and autonomous implementation. Android source is committed at `ffa1964c39d3270aacdb5e06e184b44ed0f0e86d` (preceded by `0e1880e` and `ec9d89a`); baseline was `3c81943`. No backend contract or server deployment changed in this turn.

## Result

Today defaults to recorder capture with optional phone capture. An identity-scoped controller outlives page composition; a connectedDevice foreground service retains active sessions. Vendor physical recording events drive phase/time, markers and exact-file retrieval. End waits for actual live-transfer drain, then obtains the matching device file, verifies raw data, decodes and exposes local playback/marker seeking. Home reuses consent, upload, transcript review and memory display. Download/decode/upload percentages reflect observed bytes; cloud work shows stages only.

No remote start/stop command is fabricated. Start/end remain device physical operations. Account or subject change and loss of owner access close the session. Saved raw files are preserved; stable scoped import keys prevent duplicate upload identities.

## Review and regression

Fresh reviewer inspected code plus actual SDK 1.3.02 bytecode. Fixed all three findings:

- Realtime transfer could still be draining when offline sync began. Queue now uses SDK-observed active/idle/completion state, handles transfer rejection and gives a bounded waiting failure. A requested-but-never-started realtime stream does not block offline sync.
- Late start/pause could reopen a stopped file before download. Ended identities remain terminal; controller performs side effects only for accepted transitions.
- Imported grant after authorization failure lacked foreground service ownership. Import now starts the service; tested on Android.

Final read-only follow-up found no further actionable issue in these corrections. It is not physical-device approval.

## Executed checks

- Full Android debug unit suite: **130 tests, 0 failures, 0 errors**.
- SDK-enabled debug build and instrumentation build: passed.
- Optional no-SDK `compileDebugKotlin`: passed.
- Signed internal build, lintVital, signature verification and package metadata: passed.
- Same-signature emulator upgrade using `adb install -r`: passed (no uninstall).
- Final signed APK instrumentation: **8 tests passed**, 53.716 seconds: CaptureInstrumentedTest (2), RecorderSessionTest (2), RecorderForegroundTest (1), HardwareScreenSmokeTest (1), HardwareCloudChainTest (1), RecorderHomeUploadLiveTest (1).
- Real SDK online grant/authorization twice after closing SDK: passed.
- Synthetic SDK callback test: physical start/status, markers, stop duplicate, late start rejection, delayed realtime completion and cancelled pending realtime request. Actual Android decoder/journal used; no physical Bluetooth transport.
- Foreground service: auth failure releases service, imported grant restores it; disposing/recreating Compose panel preserves connected controller.
- Real cloud upload with explicitly fictional `memory-garden/E01` speech, converted to 160-byte/20-ms Opus frames: 88,340ms. Real Android decoding, persistent capture reload, upload, transcript-review gate, test-author confirmation, ready memories, and MediaPlayer seek replay passed. Debug evidence episode `ep_8a1b52cb746544f3`; signed package with its separate local journal produced `ep_ab287e8300b84362`. Stable upload identity was checked within each journal/session; cross-install deduplication is not claimed.
- Inspected actual home/saved/review/organized emulator screenshots. Foreground service fixture UI is synthetic, not a physical device screenshot.

Evidence directory outside Git: `D:/JOB/hack/delivery/work3200-home-validation/`. Original red/green and intermediate build logs remain under `D:/JOB/hack/recorder-*.log`.

## Artifact

- Version `0.14.0-device-internal`, versionCode `20261025`, applicationId `me.remember.app.internal`, not debuggable.
- APK size 166,783,095 bytes.
- SHA256 `44f0a9d3169f642818ea9c618d0c7988dae605cfe1752b65cb5f8e8084a757d3`.
- Existing signing certificate SHA256 `9c99b41e65d934bd0dee3b111543266404b49fb7d799d43c23eb82f46d8e2f75` retained.
- Private SDK bundled; vendor archive, credentials and signing key remain outside Git.
- Desktop delivery: `C:/Users/sky/Desktop/勿忘我录音豆首页版_0.14.0/` with APK, manifest, validation report and Chinese runbook. Previous 0.13.0 files retained.
- New temporary LAN download server was rejected by automatic approval review with only `blocked by policy`; no service was started and no new download URL/QR is claimed. Deliver local APK for transfer to phone, without USB debugging.

## Physical acceptance remaining

User must exercise vivo + actual soundcore Work: scan/bind, physical start/timer, marker, physical stop, automatic exact-file download, intelligible playback, consent/upload/review/memory, tab switch, screen-off/reconnect and repeated import. Actual vendor packet framing, marker offsets and vivo power management are not established by synthetic/emulator evidence. Binding code3 means physical-confirmation timeout. The runbook describes recovery and raw-file/diagnostics export.
