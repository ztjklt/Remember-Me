# Two client tracks and on-demand help

2026-10-16 本聊天追加直接授权：本人要求把 Android 0.16.0 的自动转写／持久草稿、一次保存后累计人物分析、机器原稿与自动校对对照重构至 iOS，并优先按 Android 记忆花园的内容与操作迁移。批准必要的 SwiftUI／Swift 改造、兼容共享接口及后台任务增量，见[实施范围](../architecture/ios-android-capture-garden-parity-2026-10-16.md)。保留现有实时录音／语音、重点区间与游客权限；不以本次重构整体覆盖线上服务或启动完整 Phase 4。

2026-10-16 本会话追加直接授权：本人确认持续采集、两次按键之间为不可精简重点、其他记忆可归并、全部原音保留，并明确要求「开始吧」。批准 iOS、Backend 与 AI Core 的[持续采集／重点区间增量](../architecture/wearable-priority-capture-2026-10-16.md)及必要独立 Contract。机器转写副本可在不破坏证据的前提下清理；SDK 未提供的佩戴开录与实体按键能力仍需硬件证据，不据此启动完整 Phase 4。

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

All three collaborators have Write access to this personal repository, including the ability to create Issues, push branches, open PRs, and merge where GitHub permits. Neither `main` nor `develop` has branch protection or a repository ruleset; direct pushes are allowed, and branch protection no longer blocks force pushes or deletion. Mainline leads may batch related work rather than open and wait on one PR per module. Delegated Issues still use a PR for handoff. Keep `main` as a usable demo snapshot and use `develop` for ongoing integration.

## 2026-10-15 本人追加批准

当前会话直接批准 [v0.12 声纹与人物模型修订](../architecture/voiceprint-personal-model-contract-v0.12.md)：录音／多人录音／同手机多人 Twin 的真实声纹匹配、仅本人声音的自动对话资料更新、账号＋密语限定范围的数字托付与照护人交接核验记录，以及独立人物模型资料覆盖图。该授权不启动硬件或自动身后判定。

## 2026-10-16 双模式追加批准

Product / Integration Owner 在当前会话明确要求实施[主用户与亲友／游客双模式](../architecture/guest-access-contract-2026-10-16.md)：iOS 同机免密码游客、整段来源预览与开放、独立受限会话、范围内文字／语音问答，以及返回原主用户的账号密码复验。游客不修改本人资料或参与训练，退出清理对话，来源变更和撤权阻断旧访问。该授权包含必要共享 Backend Contract 与迁移，不启动跨设备公开入口，也不改变既有指定账号托付。

## 2026-10-16 游客暗号托付修订

Product / Integration Owner 在本会话明确说明亲友就是游客，要求「只凭暗号进入」，暗号至少包含一个具体私密细节，并要求「开始调整」。批准[游客暗号托付与 Twin 内设置](../architecture/guest-entrustment-contract-2026-10-16.md)：新建托付不绑定接收者账号，由本人在 Twin 内录入／核对暗号、指定对应亲友与完整来源，游客自然说出暗号后打开专属记忆库。批准包含独立 Contract、必要迁移、iOS 与后端调整；原账号托付不自动扩大权限，未来交接仍沿用照护人核验，不由暗号自动判定身后状态。

同日本会话要求检查后明确“修复这个问题”，授权修复限流匹配信号、完整暗号包裹泄露、跨库披露和本机上锁／音频竞态，及原照护人重复设置的幂等性。必要的兼容检测索引、独立服务端密钥配置与旧计划本人重新核验接口见上述提案追加说明；保留既有计划及授权。
