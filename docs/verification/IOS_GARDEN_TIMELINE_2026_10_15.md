# Memory Garden: Timeline, Graph And Ten Floral Artworks

2026-10-15. Direct user requests: replace list-style Garden with graph/timeline UI, allow GPT-generated assets, generate ten floral images including wreath/basket/large bouquet, and enrich the Garden with motion/particles.

## Implementation

- Native SwiftUI `MemoryGardenHome` now has Timeline/Graph browsing. Stories and people share a capture-date timeline with a continuous stem and branch nodes, without stacked cards. No search or extra landing page was added.
- Dates are explicitly **capture/recording dates**, parsed as RFC3339 and grouped in the device calendar/time zone. Unknown dates remain unknown and sort last. Free-form event descriptions are not turned into invented calendar dates.
- Graph branches use existing same-subject `graph_facts` with their complete visible evidence set. Source links, fact detail sheets, source invalidation, owner isolation, local hide/cancel/restore and original-memory management remain available. Unlinked memories remain reachable even without graph facts; no new person-to-person relation is inferred.
- Palette toolbar menu selects any of ten floral illustrations. Root artwork gently sways; seven low-opacity petal shapes drift inside its bounds. Artwork selection is view state, not an account setting or a memory classification. Per-entry artwork variation is decorative only and has no semantic/progress meaning.
- The animation uses an isolated `TimelineView`/Canvas with scheduling no faster than 24 Hz, honors system Reduce Motion and the shared motion-disabled scope, pauses on scene inactivity/view disappearance and behind the Garden's own detail/restore sheets. Decorative drawing does not receive touches or accessibility focus.
- Accessibility sizes use a native mode menu, smaller root artwork and omit secondary entry artwork to preserve reading/action space. Normal and accessibility fonts remain Dynamic Type.
- Debug component showcase contains the ten-image gallery. Existing model/provider/consent/recording logic and backend contracts were not changed. Current version metadata remains 1.12.0 / 2026101504; no physical-device install, version bump, commit or push was performed in this task.

## Generated Assets

Used the built-in **image_gen** tool, not a CLI fallback or a screenshot used as a whole UI. Ten independent transparent PNGs, copied unchanged into `apps/ios/RememberMe/Assets.xcassets`:

| Catalog | Artwork |
| --- | --- |
| GardenPaperSprig | Cut-paper flower cluster |
| GardenWreath | Floral wreath |
| GardenBasket | Flower basket |
| GardenGrandBouquet | Large hand-tied bouquet |
| GardenGlassVase | Glass bud vase |
| GardenPressedFlowers | Pressed botanical sprig |
| GardenRibbonPosy | Wrapped ribbon posy |
| GardenPetals | Flowers with drifting petals |
| GardenLinework | Linework/color-wash branch |
| GardenFloralArch | Floral arch |

Each catalog contains `artwork.png` and `Contents.json`. Exact prompts, generated-source paths and repository paths: `docs/mobile-ui/GARDEN_ARTWORK_2026_10_15.json`. The ten PNGs total about 14 MiB. Preliminary alternative sprigs remain in the generator output; they are not counted in this requested set.

Native AppKit inspection confirmed all ten source PNGs have alpha channels and transparent/nearly transparent sampled corners (nine at 0, ribbon posy at 1/255). A unit test successfully loads all ten from the compiled asset catalog. Generated illustration styles vary between flat paper and painterly botanical; no claim of strict pixel-identical style or perfect botanical geometry is made.

## Actual Verification

Xcode 27 / iOS 27 simulator, Debug, iOS 17 deployment target. Existing package cache reused; no new dependency.

- **19 MemoryGardenTests passed**, including four new cases: all ten compiled artworks exist; local capture-day ordering/unknown dates; evidence-only branch matching; bounded seven-petal animation data and invalid-time rejection. Existing source validity, subject isolation and visibility tests remain green.
- **4 UI tests passed on iPhone 18 Pro / light**: empty state does not invent data; select basket; cancel/remove/restore and graph; timeline dates/fact sheet/source navigation.
- **3 UI tests passed on iPhone SE 3 / dark**: basket selection, maximum accessibility-size story/control navigation, and timeline/fact/source navigation.
- Total: **26 targeted test executions**, comprising 19 unit cases and seven device-specific UI executions (five distinct UI cases). Not a full application regression suite.
- Actual screenshots were inspected for normal light, small dark, maximum Dynamic Type, Timeline, Graph and basket art. Fixtures are explicitly fictional, isolated and offline, without real grants or provider traffic.
- Compared two native simulator frames of the root artwork: **80,203 changed pixels** above summed RGB difference 0.01 in x=300..<906, y=600..<1230. This confirms nonstatic rendered motion, not measured FPS/GPU/battery performance.
- `git diff --check` passed. Initial build caught the digest's Sequence/Collection `.first` access and was repaired with an explicit Array before successful tests. Existing AppModel trailing-closure, existing PersonReview test actor-isolation and skipped AppIntents metadata warnings were observed; no new Garden warning was observed.

Evidence:

- `build/ios-garden-timeline-first-20261015.log` and `.xcresult` (19 unit + 4 UI, TEST SUCCEEDED).
- `build/ios-garden-timeline-small-20261015.log` and `.xcresult` (3 UI, TEST SUCCEEDED).
- `build/ios-garden-timeline-screens-20261015/manifest.json` and `build/ios-garden-timeline-small-screens-20261015/manifest.json` map native screenshots to cases.
- `build/ios-garden-timeline-screens-20261015/motion-a.png` and `motion-b.png` are the motion comparison frames.

Reproduce from root using an available simulator ID:

```sh
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -configuration Debug -destination 'platform=iOS Simulator,id=10BAAA0D-3912-4F01-9CD6-92897F1A1695' \
  -derivedDataPath build/ios-garden-timeline-20261015 \
  -clonedSourcePackagesDirPath build/ios-voice-20261014/SourcePackages \
  -disableAutomaticPackageResolution -parallel-testing-enabled NO \
  -collect-test-diagnostics never -only-testing:RememberMeTests/MemoryGardenTests \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenTimelineDatesAndGraphSourcesStayInteractive \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenArtworkMenuCanSelectBasket \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testGardenRemovalCanCancelAndRestoreWithoutDeletingMemory \
  -only-testing:RememberMeUITests/SimpleFlowUITests/testEmptyGardenDoesNotInventStories \
  CODE_SIGNING_ALLOWED=NO test
```

Not verified: physical-iPhone appearance/interaction, iOS 17 runtime, a full VoiceOver walkthrough, Instruments/FPS/CPU/GPU/battery behavior. Pause logic reuses the unit-tested shared policy, but no automated system Reduce Motion setting change or background performance measurement was claimed. Password/security/estate access behavior was not added or changed.

## Page Copy Follow-Up

The user requested removal of the visible fictional-page wording. Removed the debug preview's top banner in both normal/accessibility sizes and replaced its detail category label with Story/Person. Offline sample data remains isolated behind the existing DEBUG/UI-test route; it was not promoted into production records. Production function/data bindings were unchanged.

Two focused native UI tests passed (normal timeline/fact/source navigation with assertions that both former banner strings are absent, plus maximum accessibility-size navigation): `build/ios-garden-copy-clean-20261015.log` and `.xcresult`, TEST SUCCEEDED. Updated screenshot exports: `build/ios-garden-copy-clean-screens-20261015`. The earlier screenshots above retain historical UI copy; these exports supersede them for the banner removal. No physical-device installation was performed in this follow-up.
