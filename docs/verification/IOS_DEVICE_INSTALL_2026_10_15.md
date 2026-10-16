# iOS Device Installation

2026-10-15: at the user's explicit request, rebuilt the current workspace and installed it on iPhone 15 Pro Max "黑幕" (iOS 26.6.2).

- Before: `me.remember.personal.ios`, **1.8.3 / 2026101408**.
- After: same bundle identifier, **1.9.0 / 2026101410**. Version metadata was retained; this is a new Release build from current source, including the native Design System, not reuse of yesterday's app package.
- Fresh derived data: `build/ios-install-20261015`. Release build succeeded; `codesign --verify --deep --strict` passed. No source, provider, contract or authorization change was made for installation.
- `devicectl device install app` succeeded without uninstalling or resetting the application. Device app listing independently confirmed the installed version. Normal launch succeeded, PID 28780, with no test arguments.
- Data container path changed during installation; no assertion that its UUID stayed identical. A metadata-only listing confirmed four existing M4A recordings and their four manifests, dated October 13, remain in the application's recording directory. Recording content was not read or modified; no full before/after data integrity audit was performed.
- No microphone use, new consent, transcription confirmation, live call, voice generation or personality assessment was performed. Process launch does not constitute a visual or end-to-end functional acceptance test.

Evidence in ignored `build/`: `ios-install-build-20261015.log`, `ios-install-before-20261015.json`, `ios-install-result-20261015.json`, `ios-install-after-20261015.json`, `ios-install-launch-20261015.json`, `ios-install-recording-files-20261015.json`.

Signed main executable SHA-256: `4170eef3c46b793bc7f7b81ebb3ad0d1c6d45ea2886e3fc14b95fc00137f640d`.
