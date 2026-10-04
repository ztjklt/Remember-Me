# Agent loop verification — 2026-10-03

Current scope: user-authorized experimental Agent loop on the ordinary branch `feature/ai-agent-core`, created from the original Android branch `feature/android-capture-to-model` at `c35ede0`. Development and verification now run in `/home/qingtian/projects/Remember-Me`. This follows the user's explicit request to use the original version without an extra worktree. No push, merge or deployment was performed.

## Review and migration decisions

- **Keep `c35ede0`:** useful device-capability checks for recording retrieval and local playback. Original Capture/HTTP history and 29 Android files outside the Agent increment remain unchanged.
- **Keep the useful part of `ea37ea8`:** schema workers, shared experimental contracts, Backend authorization/persistence, Android Agent integration, regression tests and the HTTP loop. Transplant the Agent increment instead of copying the develop-based commit's existing Android code again.
- **Keep useful uncommitted prototype changes:** understanding entry after Processing, home navigation, seven-domain display shell and Repository boundary. These are included in the new Agent commit.
- **Remove superseded local inference:** `DerivedUnderstandingRepository`, its 12 count-based tests, the Memory-type-to-persona mapping, and the unused navigation parameter. The client now receives Actor/Subject-scoped Backend snapshots; EMOTION alone no longer maps to Identity.
- Preserve original project/team/roadmap documents, frozen v0.1.2 schema and original AI fixture set. The wheel smoke test merges the new shared-schema check with those original fixtures.

## Verification in the original project directory

| Actual verification | Result |
|---|---|
| Backend: `.venv/bin/python -m pytest tests -n 4 -q --tb=short` | **227 passed**, process exit 0; 12 upstream deprecation warnings |
| AI Core: `.venv/bin/python -m pytest tests -q --tb=short` | **124 passed**, 2 upstream deprecation warnings |
| Contract: `cd packages/contracts && npm test` | **11 passed**, zero failures/skips |
| Android: `./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest` | **BUILD SUCCESSFUL**; Debug **29**, Release **29** tests, zero failures/errors/skips; app and instrumentation APKs built |
| One-command demo: `services/backend/.venv/bin/python scripts/run_agent_demo.py` | Actual Backend/STT/AI HTTP: Memory 1 → revision 1 → ORIGINAL → persisted LOCKED → five dimensions → revision 2 → next Episode → revision 3 |
| Android HTTP consumer test | Actual demo payloads consumed through `HttpAgentGateway` / MockWebServer in both JVM variants |
| Wheel packaging | Both wheels rebuilt; isolated extraction smoke passes packaged Memory fixtures and experimental Persona route with contracts wheel |
| Migration checks | Agent core files match the old commit; original capture/schema/fixture baselines unchanged; both Python environments resolve contracts from the main directory; no old worktree path in `.pth` files |
| Static checks | `git diff --cached --check` passes |
| Device acceptance | Instrumentation was compiled, not executed on a device; the prior device check found no connected device or KVM |

The old worktree ran 130 AI tests and 41 Android tests per variant. The current 124 AI tests retain the original branch's fixture suite, without importing develop's six additional long-fixture tests. The current 29 Android tests remove the 12 tests for the discarded local inference. Backend, experimental-contract and live HTTP coverage are retained.

`pytest-xdist` is installed only in the local verification environment; normal `pytest tests` runs the same suite without it. Python 3.13.12; JDK 17.0.20.1; Android SDK 35 / build-tools 35.0.0 / Gradle 8.9. Existing lock selections retained; only shared `remember-me-contracts` added to service dependency locks.

Artifacts in the main directory (ignored): `build/verification/*-migration.log`, `build/agent-demo/fixture/last-loop.json`, `build/wheels/*.whl`, `apps/android/app/build/outputs/apk/debug/app-debug.apk`. Old artifacts were saved separately under `build/agent-migration-archive/` before removing their worktree.

APK SHA256: `74ea273ba2c15b27fee2ebbc2247774bd3eb32686aaae23b0a905ada8e71132a`.

Recovery backup: `/tmp/remember-me-branch-migration-20261003/` contains the original tracked patch, untracked files and a verified Git bundle with both pre-migration branch histories. The old worktree and `feature/ai-agent-core-loop` are retired after the new commit is verified; subsequent development uses the main project directory.

These are **fixture wiring and code verification**, not real Chinese STT / LLM fidelity or real-device acceptance. STT demo ignores speech and the input WAV is silence. Real adapters are configured separately; they never silently fall back to fixture. Source authority is self-declared, not identity or speaker verification. See [setup and limits](../architecture/AGENT_CORE_LOOP.md).

Contract impact: new **experimental** shared schemas and routes, disabled by default; frozen integration-contract-v0.1.2 unchanged. Consent impact: separate Cloud Twin experimental opt-in, Actor + Subject isolation, source checks before/after processing and revoke/withdraw invalidation. Migration: `0004_agent_loop` adds four Agent tables; downgrade and model parity tests passed. To stop the experiment, disable `REMEMBER_AGENT_ENABLED` / `AI_AGENT_ENABLED`; retained audit data is not silently deleted. Future team contract freeze and real provider/device acceptance remain separate.
