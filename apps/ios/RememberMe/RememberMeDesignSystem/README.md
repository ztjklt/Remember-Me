# RM Design System

SwiftUI, iOS 17+, no new dependencies. Sources are included by the existing XcodeGen `RememberMe` source directory.

- `Tokens`: semantic light/dark colors, Dynamic Type fonts, layout and animation constants. Use `action` for readable interactive text; pastel `brand` is for artwork, not small text on white. No custom letter spacing.
- `Components`: reusable native buttons, content/audio/person/recording/timeline cards, inputs, navigation wrappers, feedback and player. Pass existing bindings and actions; components do not call services or create grants.
- `Visuals`: five rounded blue petal vectors, yellow center, natural green stems, small flower sprig and state animation. Botanical colors are independent of the blue/white interface palette. Existing launcher logo/assets remain unchanged. Shape sources are the editable artwork; no bitmap page backgrounds.
- `Previews`: `DesignSystemShowcase` contains every component family, loading/disabled examples and all flower states. Debug launch argument: `--uitest-offline --uitest-design-system`. Debug settings also include a component-preview entry. Xcode previews include light/dark, large text and an explicit motion-disabled scope; this is separate from the read-only system Reduce Motion setting.

`VoiceReactiveFlower(state:audioLevel:)` accepts optional real normalized amplitude. `nil` means state-only animation. Recording uses the existing recorder meter; realtime calls currently pass `nil`, without changing the LiveKit model. Amplitude is finite/clamped/smoothed. Timeline updates are limited to 24 Hz and paused offscreen, in background, under Reduce Motion and in inactive states.

Use `RMFeedback` for persistent errors/empty/success states and `RMToast` only for supplementary confirmation. Always preserve an accessible status label outside decorative flowers. Cards have 8 pt corners; normal page sections remain unframed. Navigation stays native. Use `RMSegmentedControl` when options must fall back to a menu at accessibility sizes.

`Ink` and `ActionButton` are compatibility entry points, so old review/connection screens inherit the new semantic colors/buttons without changing workflow behavior. New screens should reference RM tokens directly.

Botanical reference: [RHS Myosotis sylvatica](https://www.rhs.org.uk/plants/41558/myosotis-sylvatica/details): small clustered flowers and yellow/white eyes. The illustrations retain their original five rounded blue petals, yellow center and green stems, without characters or heavy 3D shading.

Verification and limits: `docs/verification/IOS_DESIGN_SYSTEM_2026_10_14.md`.

Memory Garden additionally uses ten GPT-generated transparent botanical assets with `GardenArtwork`, a native stem/branch timeline and evidence graph, plus seven bounded Canvas petals around its selected root artwork. `GardenArtworkImage` presents the original assets without recoloring; the style menu changes composition. Prompts and source paths: `docs/mobile-ui/GARDEN_ARTWORK_2026_10_15.json`. Garden-specific checks and limits: `docs/verification/IOS_GARDEN_TIMELINE_2026_10_15.md`. Its gallery is included in the component showcase.

2026-10-16: iOS, Android and the web workbench share blue `#2563EB` actions, white cards, `#F5F9FF` backgrounds and navy `#142C4D` text. Dark appearance uses navy surfaces with pale blue actions. Keep success/danger semantic colors distinct. The `Rm*` asset colors mirror the Swift tokens. See `docs/verification/BLUE_WHITE_THEME_2026_10_16.md` for checks and delivery limits.
