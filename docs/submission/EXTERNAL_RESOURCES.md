# 外部资源与交付边界

完整源码包含所有已跟踪源码、图片、文档、测试、锁文件；不包含虚拟环境、编译缓存、运行数据库或供应商秘密。

| 资源 | 当前状态与接手方式 |
| --- | --- |
| Android Soundcore SDK 1.3.02 AAR | 已集成进交付 APK；源码通过 Gradle 参数引用。原文件在原维护机 `D:/JOB/hack/local-sdk-inspection/soundcore-1.3.02.aar`，SHA-256 `f9ca8e8dd6703d10dd55426022068113412e2a23a174c5cc8b59d99be0878d3a`。厂商分发文件未直接放进公开 GitHub；授权队友可由拥有者提供原 SDK。接口检查/接入说明已在 `apps/android/docs` 和 `tools/delivery/audit_soundcore_api.py` |
| sherpa-onnx Android AAR | 已跟踪于 `apps/android/app/libs/`，完整源码包包含 |
| Paraformer 本地权重 | 大型 ONNX 权重不在 Git；本次云端 ASR 不依赖它。旧本地识别实验请按相应模型说明另行准备，不能把有 AAR 当成有全部模型 |
| BGE 检索权重 | Python retrieval extra 及配置在源码；权重按模型名/缓存下载。旧主机路径是私有环境，不打包整个 Hugging Face 缓存或令牌 |
| DeepSeek/ASR/小米凭据 | 字段和配置模板齐全；值留在服务器 `/etc/remember-me/`。接手方用自己的授权凭据，或由拥有者经私密渠道交接 |
| Android 发布签名 | 原维护机 `C:/Users/sky/Desktop/勿忘我私有迁移资料_2026-10-16/01_APK签名`；签名私钥不公开，APK 可直接安装体验 |
| 运行数据库/原音 | 当前服务器私有存储；旧测试空间已停用，备份在 `/var/lib/remember-me/legacy-demo-archive-20261017/`。不公开真实凭证、完整账号表或旧混杂材料 |
| 演示素材 | `chen-fictional-materials.json` 提供当前虚构人物剧情素材，不含登录凭据。材料是模拟设定，不是真人传记；音色是合成声音，不声称真人克隆 |

若交付对象只需要审阅/修改 Python 后端，完全不需要 Android SDK AAR、发布私钥或现有生产数据库。完整源码、运行说明和空配置模板已足够建立自己的环境。

## 进行中的同工作区改动

交接快照同时发现旁侧任务正在改人物事实入口、对话视角与相关测试。Release 证据包附 `work-in-progress.patch` 和文件清单，保存快照时的差异，供接手 AI 审查；它不进入稳定源码包，不代表通过全部验证或已部署，也不要在后续已包含这些提交的分支重复应用。
