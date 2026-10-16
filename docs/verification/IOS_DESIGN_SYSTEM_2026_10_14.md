# iOS Design System Verification

Date: 2026-10-14. Native SwiftUI implementation, not a bitmap mockup.

## Delivered

- `apps/ios/RememberMe/RememberMeDesignSystem`: adaptive tokens, reusable buttons/cards/inputs/native navigation/feedback/audio player, editable five-petal blue/yellow flower vectors and sprig, state animation, component showcase and Xcode previews. No new package dependency.
- Existing recording home, recording/review, memory library/detail, garden, Twin chat and call presentation upgraded. Original recordings, evidence, corrections, deletion, consent, voice enrollment/revocation and failure paths remain available.
- Memory overview opens original/source/correction details via a separate button. Call conversation details open from a toolbar icon; both main call and detail sheet retain real hangup controls.
- Recording accepts actual recorder levels. Realtime voice remains state-only (`audioLevel: nil`); this work does not alter LiveKit, backend payloads or authorization gates.
- Debug showcase: My/组件预览 or `--uitest-offline --uitest-design-system`. Fixtures are isolated test data, not a person's records or real transmitted calls.

Plan: `docs/mobile-ui/IOS_DESIGN_SYSTEM_PLAN_2026_10_14.md`. Integration: `apps/ios/RememberMe/RememberMeDesignSystem/README.md`.

## Executed Checks

Xcode 27, iOS 27 simulator runtime; deployment target remains iOS 17. Existing LiveKit checkout reused; simulator code signing disabled.

| Check | Result | Evidence under `build/` |
| --- | --- | --- |
| Simulator Debug build | Passed | `ios-design-system-build-fixed-20261014.log` |
| Initial unit suite | 105 passed | `ios-design-system-unit-20261014.log` and `.xcresult` |
| iPhone 18 Pro, light, focused native UI suite | 11 passed | `ios-design-system-ui-20261014.log` and `.xcresult` |
| iPhone SE 3, dark, after layout fixes | 6 passed; call detail check still failed | `ios-design-system-small-final-20261014.log` and `.xcresult` |
| Final complete unit suite on current workspace | 119 passed | `ios-design-system-final-regression-20261014.log` and `.xcresult` |
| Final SE call detail/open/hangup regression | 1 passed | Same final regression bundle |
| Whitespace check | Passed | `git diff --check` |

The seven selected small-screen cases have passing final outcomes across the last two runs, not one final all-UI batch. They cover component states, memory details, maximum accessibility-size home/composer, default-voice consent at normal/maximum size, garden accessibility size, and call details/hangup.

The larger-screen suite also checked four native tabs, denied-microphone recording, chat keyboard/composer, search connection gating, pending voice-sample submission gating, and garden removal/cancel/restore. Unit checks include existing subject isolation/consent/audio state tests and new amplitude sanitization, animation pause policy, date parsing and light/dark semantic text/action contrast tests.

## Repairs And Diagnostics

- A preview initially attempted to set the read-only system Reduce Motion environment. Replaced it with an opt-in `rmAnimationsDisabled` scope; actual system Reduce Motion remains honored.
- Small-screen content could be partly hidden behind pinned call controls. Moved conversation details to the native toolbar. The consent test scrolls the whole switch above the pinned area, taps the actual switch and asserts value `1`; it does not bypass consent.
- Main-call/detail-sheet controls now have distinct accessibility identifiers. The final test taps the detail-sheet hangup and verifies return to idle.
- Added an artwork-specific pale-eye token so the flower's eye does not turn dark with container colors.
- An early failed small-screen run stalled collecting diagnostics and was terminated after case results were logged. Later runs use `-collect-test-diagnostics never`; its incomplete bundle is not counted as passing.
- One intermediate build encountered a test constructor missing `question_bank` during concurrent workspace edits. The next build and final suite passed with the updated fixture; this UI work did not change that contract/model.
- Existing AppModel trailing-closure and some existing test-isolation warnings appeared in intermediate builds. Final incremental run reported AppIntents metadata extraction skipped; no new Design System compilation warning was observed.

Earlier failed/interrupted logs remain under `build/ios-design-system-small-*.log`; final success does not erase them.

## Visual And Motion Inspection

Inspected actual simulator PNGs: small dark memory overview/detail, main call/detail, maximum accessibility-size recording/chat/consent, large light home/keyboard, and component states. Exported attachments and filename manifests: `build/ios-design-system-screens/`.

Current captures:

- `build/ios-design-system-screens/home-current-light.png`
- `build/ios-design-system-screens/small-final/93A5D8D4-36CD-4134-94A6-C5100F0EB5D3.png` (memory overview)
- `build/ios-design-system-screens/final-regression/5A6720B6-89E5-4195-AEBD-0D336074CCD3.png` (call)
- `build/ios-design-system-screens/final-regression/6649161F-E706-40B3-9199-2FDAC636FA22.png` (call details)

Compared `call-motion-a.png`/`call-motion-b.png` with AppKit pixel reads: 7,579 pixels changed above RGB-difference threshold 0.01 in the 310x310 flower region (x=220..<530, y=300..<610). This verifies nonstatic rendered animation, not FPS/performance or audio reactivity. No fake microphone amplitude was supplied.

Timeline scheduling is limited to 24 Hz; code pauses when the view disappears, scene is inactive, Reduce Motion is on, or state is inactive. The call flower also pauses behind its detail sheet. Unit tests exercise pause predicates, not an Instruments or physical-device accessibility measurement.

## Reproduce

From repository root, use an available simulator ID:

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -configuration Debug -destination 'platform=iOS Simulator,id=FB5B94AC-8CFA-41D7-B710-AD11597433FD' \
  -derivedDataPath build/ios-design-system-20261014 \
  -clonedSourcePackagesDirPath build/ios-voice-20261014/SourcePackages \
  -disableAutomaticPackageResolution -parallel-testing-enabled NO \
  -collect-test-diagnostics never -only-testing:RememberMeTests \
  -only-testing:RememberMeUITests/RMDesignSystemUITests \
  CODE_SIGNING_ALLOWED=NO test
```

## Limits

- No physical-iPhone installation, real microphone/earphone/LiveKit/provider round trip, voice-quality check, or FPS/CPU/GPU/battery profiling in this task.
- Runtime checked on iOS 27 only; compilation targeting iOS 17 does not prove iOS 17 device behavior.
- VoiceOver semantics/Dynamic Type implemented, but no full physical-device VoiceOver audit. Reduce Motion stopping logic is unit-tested, not a system-settings automation result.
- Optional owner-chosen password/protected-memory behavior remains the separate protected-garden security proposal. No encryption or estate access was implemented here; a cosmetic lock is not presented as security.
- No backend/Android migration, provider or cross-module contract change introduced by this upgrade. Existing unrelated worktree changes preserved; no commit or push made.
