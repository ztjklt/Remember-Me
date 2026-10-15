# 交接验证（2026-10-15）

> **本日后续重新验收：** [ECS＋0.12.1 同步验证](CLOUD_SYNC_RESULTS_2026-10-15.md)新增 PostgreSQL 718 项通过、恢复检查、真实 ASR/纠错/修订/分享及 Android 语音实跑。当前[可下载签名 APK](ANDROID_0121_QUICK_START_2026-10-15.md)已发布。下表是早先本地交接记录，不把其“未重跑／未公开”沿用为当前状态。

对当前 `codex/continuous-voice-20261014` 工作区重新检查；准确范围见 [交接总览](TEAM_HANDOFF_2026-10-15.md)。本表区分重新执行的测试与已保存的历史真实模型记录。

| 本次检查 | 结果 | 说明 |
|---|---|---|
| AI Core 完整 pytest | 510 通过 | 55.35 秒；测试子进程不继承本机 SOCKS 代理，未修改全局网络配置 |
| AI Core wheel 构建及安装布局/HTTP smoke | 通过 | 独立 wheel 内 fixture、合约和接口可运行 |
| Backend 完整 pytest | 712 通过、6 跳过、无失败 | 本地 SQLite；6 项条件测试跳过，不计作 PostgreSQL 已验证 |
| Contracts `npm ci` / `npm test` | 15 通过 | 安装审计 0 漏洞；不等于所有业务语义正确 |
| Android 单元测试 | 114 通过 | 审查修复后再次全部通过 |
| Android debug 构建 | 通过 | 修复后 `testDebugUnitTest assembleDebug` 成功，63 秒；不需要内部签名 |
| Android internal 签名构建 | 0.12.1 构建及签名验证通过 | 原签名、版本码 20261023、源码 `6efb72d`；107 秒。首轮缺少签名环境失败，随后使用已有私有签名配置重建成功 |
| 凭据检查 | 候选文件与三项未推送提交未发现真实凭据 | 同时检查 token/私钥形式及本地配置值的精确匹配；虚构测试字符串单独辨认 |
| 独立代码审查 | 发现并修复一项旧服务器兼容问题 | 快速模式不再默认开启；能力未开放时隐藏快速开关，旧 reviewed 路线仍可直接开始 |
| GitHub CI | 推送后按实际 SHA 查看 | 不沿用上次提交的绿灯 |

本次没有重新执行真实模型语义评测、PostgreSQL 集成、模拟器旅程或实体手机验收。已有真实调用与原速视频作为带日期的证据一起提交，结论和未通过项未被改写。

签名候选包为 `remember-me-0.12.1-internal.apk`，SHA-256 `37260ac2bae5e2c1165cfb3af3c404f47fc4a206bef4c8010e2e9ce5427e9dc3`。[构建清单](evaluations/handoff-20261015/apk-manifest.json)记录源码提交、签名证书及服务地址。这个包保留在本机构建输出，本次未替换公开 Release；后续应完成与 ECS 新服务组合的旅程验收再发布。163.9 MB APK 不放普通 Git 历史。

本次自动测试日志保留在忽略目录 `services/backend/var/handoff-20261015/`、`services/ai-core/var/handoff-20261015/`；公共 CI 提供可下载的运行日志。应用构建来源、服务器发布来源与模型运行时间必须分别记录。
