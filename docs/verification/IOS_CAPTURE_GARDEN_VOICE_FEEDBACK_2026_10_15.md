# iOS capture, garden, keyboard and guided voice feedback

2026-10-15. Direct Product / Integration Owner feedback authorized these iOS interface changes. Delivered version: **1.9.1 / 2026101501**.

## Result

- Recording home shows the forget-me-not flower, Start Recording and a single My Recordings card. Local and unmatched server recordings move behind that card; text Episodes remain excluded. The previous draft can still be reopened there. Removed the redundant “原音已保存在手机，可以继续转写。” home message and connection notice from this page.
- The Memory tab opens Memory Garden directly. Removed the separate library/search landing page and garden search field. Stories, people and a memory graph remain available, with details and original sources reachable.
- Graph display consumes the existing optional v0.2 `graph_facts` from the person-model snapshot. Only same-subject facts whose complete evidence set resolves to currently displayed, ready memories are shown. Lines connect facts to their original evidence; no person-to-person relationship is invented. Older snapshots without graph facts decode to an empty graph. Account changes clear graph state.
- Twin has a visible keyboard-dismiss control and tapping its conversation area dismisses the keyboard. Leaving the view, opening panels, switching tabs and backgrounding dismiss editing; drafts remain. Recording review, voice sample correction, connection, memory correction and chat-history screens have keyboard toolbar controls and interactive scroll dismissal.
- Voice enrollment displays a fixed reading prompt. An intentionally finished reading keeps that prompt with the sample; the person listens and confirms sole-speaker and text agreement, then explicitly submits under the existing Voice grant. There is no mandatory retyping or extra STT request on this path. Optional correction remains collapsed; changes reset the confirmation. Legacy samples without text offer rerecording. Interrupted/background recordings retain audio without asserting that the full prompt was read. Sample text and prompt restoration remains scoped to the original owner.

## Actual verification

Final simulator run: `build/ui-feedback-20261015/verified.xcresult`, **TEST SUCCEEDED** on iPhone 18 Pro / iOS 27.0.

- ECSConnectionTests: 35 passed.
- LocalRecordingTests: 22 passed, including prompt restoration and subject isolation.
- MemoryGardenTests: 15 passed, including complete-source graph filtering and compatibility with older snapshots.
- SimpleFlowUITests: 7 passed: archive/garden entrances, keyboard dismissal and draft preservation, guided sample confirmation and correction, legacy rerecording, microphone denial, garden removal/restoration and graph display, and four main tabs.
- Exported UI screenshots inspected for recording home, guided voice confirmation, graph source connections and keyboard dismissal. Fixtures are explicitly fictional and do not create a real grant, recording or voice clone.

Command used for the final run (the seven selected UI method names are recorded in `verified.log`):

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=10BAAA0D-3912-4F01-9CD6-92897F1A1695' \
  -derivedDataPath build/ios-feedback-20261015 CODE_SIGNING_ALLOWED=NO \
  -parallel-testing-enabled NO \
  -only-testing:RememberMeTests/ECSConnectionTests \
  -only-testing:RememberMeTests/LocalRecordingTests \
  -only-testing:RememberMeTests/MemoryGardenTests \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testRecordingArchiveAndGardenHaveSeparateDirectEntrances \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testKeyboardCanDismissAndTabSwitchPreservesDraftWithoutReopening \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGuidedVoiceSampleCanConfirmWithoutTypingAndEditingResetsConfirmation \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testLegacyVoiceSampleOffersRerecordingWithoutMandatoryTyping \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testRecordingStartsFromOneTapAndDeniedMicrophoneKeepsNoAudio \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenRemovalCanCancelAndRestoreWithoutDeletingMemory \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testFourChineseTabsKeepCoreFlowAndHideUnfinishedEntries \
  -resultBundlePath build/ui-feedback-20261015/verified.xcresult test
```

Initial build caught a missing closing brace, fixed before running tests. The first keyboard test attempted to tap the system tab bar while the keyboard hid it; corrected to exercise the reachable panel/close route, explicit dismissal, tapping the conversation and subsequent tab switching. Actual background/tab dismissal handlers remain present, but the test does not claim it can tap a hidden tab. A graph assertion initially queried an `Other` container although SwiftUI exposes its identified descendants as text/buttons; corrected after inspecting the UI hierarchy. Earlier failed bundles and logs remain in `build/ui-feedback-20261015`; the final run passed all 79 selected checks.

## Device delivery

Release build passed with:

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -configuration Release -destination 'generic/platform=iOS' \
  -derivedDataPath build/ios-install-20261015 build
```

`codesign --verify --deep --strict` passed. App metadata was independently read as 1.9.1 / 2026101501. Signed executable SHA-256: `274aa7aa41753313ac279a19d2b4894aad826a6b46c569743f2754b5df990b8c`.

Covered the existing app on iPhone 15 Pro Max “黑幕” using `devicectl device install app`, without uninstall or data reset. Device app listing verified the change from 1.9.0 / 2026101410 to 1.9.1 / 2026101501. Normal launch succeeded, PID 28993, with no test arguments.

Metadata-only before/after checks found the same four M4A recordings and four `.recording.json` manifests, with matching names, byte sizes and modification dates. Audio/transcript content was not read; this is not a byte-for-byte integrity audit. Evidence is in ignored `build/ui-feedback-20261015`: release/test logs, xcresults, installation/version/launch JSON and recording-file listings.

## Scope and remaining human check

iOS only. Existing uncommitted workspace work was preserved. No shared schema, backend deployment, provider, account, consent or existing recording was changed. Graph facts use the existing adapter and Contract. Voice samples stay outside the Memory/Person pipeline.

Actual person reading, upload/clone quality, similarity listening and physical-device keyboard feel remain for the person to try in this installed build. Simulator fixtures and successful process launch do not prove those experiences.
