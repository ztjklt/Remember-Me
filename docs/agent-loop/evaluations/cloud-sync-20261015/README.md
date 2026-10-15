# 本轮云端与手机证据

全部人物材料为已获准公开的虚构测试；运行配置、Key、登录 token、签名私钥、数据库和备份原件不随仓库发布。

| 文件 | 核对什么 |
|---|---|
| [apk-manifest.json](apk-manifest.json) | 安装包哈希、来源提交、签名、HTTPS 地址 |
| [server.json](server.json)、[switch.json](switch.json) | 四服务同版与启用范围；切换记录 |
| [postgres-summary.json](postgres-summary.json)、[restore.json](restore.json) | 718 项 PostgreSQL 测试、38 个原音恢复与哈希检查；JUnit 原件留在本机/ECS |
| [proofreading.json](proofreading.json) | 真实机器稿、自动稿、修订清单、确认后 8 条记忆、书面修订后回答 |
| [revision.json](revision.json) | 新音频真实 ASR、关联修订与确认后材料 |
| [sharing.json](sharing.json)、[reader-revision-answer.json](reader-revision-answer.json) | 三轮撤权和最终重新分享；亲友只引用新材料 |
| [twin-owner.json](twin-owner.json) | 记录者人物模拟、新答案播放、来源和退出清理 |
| [twin-reader-missing-basis.json](twin-reader-missing-basis.json) | 相关补录未分享时隐藏理解；当次没有发起问题 |
| [twin-reader-first-question-failed.json](twin-reader-first-question-failed.json) | 分享后首问审阅失败 |
| [twin-reader-repeated-question.json](twin-reader-repeated-question.json) | 同题复测、原音播放与清理；答案正文偏强推断另记，不计全部正确 |
| [voice-pipeline-timing.json](voice-pipeline-timing.json) | 原路线三轮实际可听等待 |
| [voice-step-initial-timing-invalid.json](voice-step-initial-timing-invalid.json) | 首次 Step 运行；打断时间戳有竞态，**不能用于打断验收或发布视频** |
| [voice-step-retest-timing.json](voice-step-retest-timing.json) | 修正测试读取后复测，实际等待与插话时间 |

完整结论见[同步结果](../../CLOUD_SYNC_RESULTS_2026-10-15.md)。文件中的 `ok` / `status=passed` 是当次脚本所覆盖的流程断言，不是人物语义准确率；所有答案另外核读。识别与提取失败重试、计时和脚本断言调整均在结果记录中保留。

`proofreading.json` 的书面修订通过 App 模型方法调用，`revision.json`/`sharing.json` 为真实 HTTPS 接口测试；不把这些叫作全程手点 App。`twin-*.json` 使用实际 Compose 点击、普通账号、真实接口；保存答案/资产读取如有则使用现有 App 模型方法。语音以预录 PCM 注入 App 通道，非实体麦克风。
