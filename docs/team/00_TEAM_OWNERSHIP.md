# Two client tracks and on-demand help

Product Owner decision, 2026-09-26. This is the current delivery model and the platform amendment to PRD v3.0: iOS and Android are both active client tracks. PRD v3.0 still defines product behavior and consent; `packages/contracts` remains the shared interface source of truth. The former person-to-Backend, AI Core, and Voice assignments in the Team Development Guide, kickoff, and individual briefs are historical.

## Leads

| Track | Lead | Current starting point |
| --- | --- | --- |
| iOS | 张天霁 (`@ztjklt`) | Authorized client track; no iOS app project is committed yet |
| Android | 刘修贤 (`@shuziyuxingxing-stack`) | Existing Kotlin / Jetpack Compose app and recording work |

These are the two main product routes. Backend, AI Core, and Voice are shared capabilities, not standing people, queues, or mandatory independent deployments. The two leads can move their client work forward independently against the shared Backend Contract. They coordinate only a concrete shared-interface change or integration conflict, rather than waiting for repeated cross-team acceptance.

康欣 (`@centraler`) and 王昊宇 (`@qingtian-4`) have no standing task queue. When a lead encounters a bounded design or implementation problem that would take too long alone, either available contributor may take a new, explicit Issue. As of this decision, no new small task is assigned to them. Closing the old execution queues and pausing unstarted Issues does not erase past commits or PRs.

## Small Issue handoff

An on-demand Issue states the concrete outcome, code or Contract to reuse, scope, and one observable completion check. Assign one available contributor for that Issue only. The contributor works from current `develop`, opens a focused PR, and includes setup notes so either lead can use the result locally. The leads can continue their own routes while the Issue is in flight. Existing open PRs retain their authors and can be triaged separately; they do not recreate permanent module ownership.

No cross-module Contract change happens silently: put the proposal in the Issue and get Product Owner approval first. Avoid duplicate implementations of the same shared capability. Neither mobile client holds provider secrets; STT, LLM, and Voice providers stay behind server-side adapters. Recording and voice-clone consent remain separate, and Episode provenance and Subject/Actor isolation remain intact.

## Fast verification and repository access

CI and peer review are useful signals but are not required merge gates on `develop` or `main`. A lead or contributor records the shortest relevant result, including a failure if one remains; do not call an unrun check successful. Check a real device when changed native behavior needs it and once for the selected end-to-end demo. Do not repeat the same device test across people, PRs, or both platforms solely for sign-off. The Phase 1 product claim still requires a real recording to pass through upload, STT, Memory extraction, and readback on one client.

All three collaborators have Write access to this personal repository, including the ability to create Issues, push branches, open PRs, and merge where GitHub permits. `main` and `develop` have no required review or status check; force pushes and branch deletion remain disabled. Mainline leads may batch related work rather than open and wait on one PR per module. Delegated Issues still use a PR for handoff. Keep `main` as a usable demo snapshot and use `develop` for ongoing integration.
