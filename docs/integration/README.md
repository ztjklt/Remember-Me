# 比赛前双端整合入口 · 2026-10-15

**Android 已有可下载安装的 0.12.1；iOS 最新后端也在线，但最新 iOS 客户端源码尚未在本次扫描的分支中找到。两端不能直接换地址或整分支覆盖。**

本目录是本次交接的入口，不替代原始验收记录。先读结论，再按需要进入接口和操作细节。

1. [严格复盘、功能矩阵与明天整合顺序](COMPETITION_REVIEW_2026-10-15.md)
2. [技术框架、数据规则与双端接口对照](PLATFORM_PROTOCOL_2026-10-15.md)
3. [UI 对齐、待补交清单与可交给下一位 AI 的任务说明](NEXT_DEVELOPER_2026-10-15.md)
4. [本轮检查与原始证据](evidence/2026-10-15/README.md)
5. [Android 下载、账号和完整操作](../agent-loop/ANDROID_0121_QUICK_START_2026-10-15.md)
6. [Android 实跑截图](../agent-loop/screenshots/cloud-sync-20261015/README.md) · [APK 与原速视频](https://github.com/ztjklt/Remember-Me/releases/tag/demo-android-0.12.1-20261015)

继续开发的当前入口：`codex/continuous-voice-20261014` / [PR #94](https://github.com/ztjklt/Remember-Me/pull/94)。**PR 保持未合并**。本轮补充交接与检查工具，没有把声纹分支合入 Android，没有重部署 ECS 或 CloudBase，也没有将旧 APK 改名冒充新构建。

## 明天会议可直接讲的三句话

- 核心是“有依据、能纠正、能保留不同视角的人物记忆”，花田和带声音的 Twin 是体验入口；不是声纹、Agent 数量或分类数量本身。
- Android 已能展示故事、纠错、修订、亲友授权和连续对话；人物质量、模型稳定性、真实手机回声仍有缺口，语音尚未稳定两秒。
- iOS 已另行推进声纹、LiveKit、自然聊天入库和托付。先补齐实际客户端源码，明确两端不同的自动入库规则，再分模块迁移；比赛演示先各用已经验证的服务。
