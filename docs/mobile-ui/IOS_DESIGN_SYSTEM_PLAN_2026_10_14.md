# iOS Design System Upgrade

## Existing implementation

- `RootView` uses native `TabView` and four `NavigationStack` routes: recording, memories, Twin and settings. Older dashboard views remain available in source.
- `AppModel` owns recording, transcription review, original playback, search, chat and consent. `PersonReview` and `MemoryGarden` retain their own scoped projections. Keep these bindings and persistence paths.
- `TwinVoiceCallModel` owns the existing LiveKit connection and state machine. UI changes must preserve start gates, mute, interruption, ending, route selection, errors, voice enrollment and revocation.
- `Views.swift` contains the shared `Ink`, `ActionButton`, original player and brand, mixed with page-specific spacing and colors. Extract presentation primitives and leave workflow methods in place.
- Recording exposes real `meterLevels`; realtime voice exposes call states, not a published audio amplitude. Realtime flower animation is state-driven until a real level adapter is supplied.
- Memory Garden already has bitmap flower assets and working source/removal/restore flows. Preserve those flows while replacing the visible decorative flowers with the shared vector language.

## Implementation

1. Add `RememberMeDesignSystem` under the existing app target: semantic adaptive colors, Dynamic Type fonts, spacing, shape, shadow and motion tokens.
2. Add shared button, card, input, navigation, audio and feedback primitives with native accessibility and a complete debug-only showcase.
3. Draw five rounded petals, a yellow eye and small grouped blooms using SwiftUI vectors. Pause animation offscreen, in background and under Reduce Motion. Keep amplitude optional and sanitized.
4. Upgrade the existing recording home, memory library/detail, recording/review, Twin chat and realtime call screens. Keep detailed evidence and corrections behind deliberate controls; preserve distinct Original/Simulation/Conversation/Unknown labels wherever answers are displayed.
5. Build and run focused unit/UI checks on isolated simulator fixtures. Inspect light/dark, small/large screens and accessibility sizes. Report device/audio limits truthfully.

## Boundaries

No backend payload, provider, audio transport, storage migration or automatic consent changes. Existing four routes and functional entry points remain. Optional protected-memory/password behavior follows the separate protected-garden proposal; this visual upgrade does not claim to implement data encryption by adding a cosmetic lock.

## References

- Botanical morphology: [RHS Myosotis sylvatica](https://www.rhs.org.uk/plants/41558/myosotis-sylvatica/details).
- Native motion: [Apple Motion HIG](https://developer.apple.com/design/human-interface-guidelines/motion), [TimelineView](https://developer.apple.com/documentation/swiftui/timelineview).

Execution results belong in `docs/verification/IOS_DESIGN_SYSTEM_2026_10_14.md` after checks run.
