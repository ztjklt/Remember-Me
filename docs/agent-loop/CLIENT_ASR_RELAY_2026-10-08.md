# 客户端 ASR 接力：实现、实跑与交接

核对日期：2026-10-08。实现提交 `b2f827b`，分支 `codex/agent-integration`。未 push、未合并，未修改饮食项目。

## 这次采用的分工

电脑客户端通过当前已验证的网络调用 Groq `whisper-large-v3`；ECS 不再承担 ASR 外部调用。客户端交付完整原音和原始机器稿，后端继续负责本人核对、微信 DeepSeek 整理、记忆保存、人物候选、问答及权限。

不是重新启用本地 Whisper，也不是把模型密钥装进 APK。当前实现的是受操作者控制的电脑工具；Android/iOS 的自动接力尚未接入。

新增 `POST /api/v1/episodes/client-transcribed`（multipart）及 `REMEMBER_STT_BACKEND=client`。字段及兼容约定见 `docs/architecture/client-asr-capture-proposal.md`。

- 原音 SHA256 必须匹配机器稿声明；身份、人物空间所有权及录音授权仍由服务端验证。
- 原始转写与简体核对稿分别保存；客户端模型来源明确标为 `client_reported`，不是服务器验证的逐字音频对齐。
- 初次上传进入等待核对，不排队服务器转写、不调用云端提取。完成原有 transcript-review 确认后才继续。
- 幂等键同时绑定音频和机器稿；重试不能换一份文字覆盖历史。
- client 模式的旧纯音频入口明确拒绝，不偷偷用 fake 或其他服务替代。
- 工作台显示客户端模式，禁用旧的直接上传整理入口；已导入故事仍可核对、查阅和操作。网页录下的新原音目前需下载后交电脑工具，不是已经无缝的一键体验。

## 本次真实结果

使用一段既有小米合成的 **21.44 秒虚构音频**，不是私人笔记。电脑实际 Groq 请求 HTTP 200，约 2.418 秒；请求模型 `whisper-large-v3`，响应未报告模型名称。没有用创作原稿替换 ASR。

音频 SHA256：`683cee4e0810fbf8c4d3ac5a9dc0471b9a9bd805054f7a7ae4ea74f801b5c65b`。

因 ECS 文件上传暂受浏览器扩展限制，继续在**独立本机 ASGI + SQLite 空间**执行真实业务验收，调用现有真实微信 AI Core（`Deepseek-v4-flash`）；不是 ECS/PostgreSQL 验收。

| 环节 | 本次结果 |
|---|---|
| 原音与实际机器稿上传 | 成功；来源 IMPORT |
| 核对前零记忆 | 通过；原始机器稿保留 |
| 技术确认后实际整理 | 4 条记忆持久保存，均有原文证据 |
| 人物归纳 | 3 条待确认候选，均有来源，只有 1 次独立讲述，不声称稳定人格 |
| 已知问答 | 茶与不加糖信息保留，返回 ORIGINAL 和实际来源 |
| 未知问答 | 银行卡密码问题返回 UNKNOWN |
| 原音回读 | 音频字节哈希与上传前一致 |
| 独立读者 | 私密原音 404；授权后音频和问答可读 |
| 撤权 | 连续 3 轮：旧音频及该读者旧答案均 404 |

接口/规则验收记录共 53 个步骤，未通过步骤为 0。首次运行曾因验收脚本的 Windows 默认编码报错，修正为显式 UTF-8 后从检查点恢复；失败日志保留。这不是 53 个相互独立的模型质量案例。

**质量核查仍有未通过项，因此不能称整个产品完全验收通过：**

1. 原音中的待核对表述被转写成“我先把搬家的年份记作2010年……后来要找旧合同合队”。ASR 的“合队”保留，没有伪造人工听读修正。
2. 提取结果把这段归纳为“我2010年搬到苏州”，人物候选也缺少暂记/待核对语气。来源还在，但结构化内容保留不确定性不够，须继续修正提取和归纳质量控制。
3. 喝茶问题引用了整段转写，事实和引文能对上，但回答过长、来源粒度粗。这不等于回答体验合格。
4. 人物候选保持 pending；技术测试没有代替本人确认，不声称人工听读通过。

## 自动回归

- 后端：389 passed，3 skipped（本机没有配置 PostgreSQL 测试库），0 failed。
- 电脑接力工具：8 passed。
- 工作台相关 Node 检查：7 passed。
- 复核修复：client 模式不再误标“假数据”；旧录音任意 metadata 不会因新的 receipt 字段触发幂等读取错误；上传检查点不能误用于另一服务或空间。

规则测试中的 fixture AI 与上述真实微信调用分开记录；没有用 fixture 充当真实模型验收。

## 电脑端使用

在仓库根目录，用已有 backend Python 环境运行：

```powershell
python tools/client_asr_capture.py transcribe --audio <原音路径> --out <机器稿JSON路径> --confirm-audio-export
python tools/client_asr_capture.py upload --draft <机器稿JSON路径> --base-url https://<已部署服务> --session-file <受保护的身份JSON> --subject-id <人物ID> --consent-id <录音授权ID> --idempotency-key <本次唯一键> --receipt <上传回执路径>
```

Groq 配置只从现有被忽略的 backend `.env` 读取；身份文件使用现有 `actor_token`，不要把它写在命令行或发送给别人。上传只保存待核对记录，不自动提交本人确认。自有 CA 使用 `--ca <证书路径>`，不跳过 TLS 校验。

已成功的机器稿检查点按原音哈希复用；失败或结果不明的 ASR 尝试需先检查，不能反复重发。上传失败可用同一幂等键恢复。

## ECS 当前状态与下一步

当前实读：旧版 `7853d00` 的四个服务 active，内部 HTTPS ready；本次检查时 0 个账号、无录音处理任务。**本轮尚未部署 b2f827b，也未在 ECS 创建上述测试资料。**

上传阻塞：Edge ChatGPT 扩展未允许文件 URL 访问；正常的 Workbench 登录已恢复，但浏览器文件选择器无法上传。已请用户开启这一个权限，未修改网络入口、注册开关或现有博客。

部署材料位于 `D:/codex_work/remember-me-aliyun-deploy-20261008/`：

- `remember-me-b2f827b.tar.gz`：177 个运行文件，14,624,322 字节；SHA256 `db4827467224ca826cbf37448020386962a62c644f258ef06833a2adf8b2d805`；现有配置密钥扫描通过，不含 .env/数据库。
- `activate-client-asr-b2f827b.sh`：先核对旧发布与空任务队列，再备份数据库和配置，切换新目录；启动失败恢复旧 symlink/config。不改变公网、注册、证书及云资源。
- `client-asr-acceptance-b2f827b.tar.gz`：实际原音、机器稿与验收脚本，不含账号、模型密钥或标准答案。具体哈希以旁边 manifest 为准。
- `accept-client-asr.py`：服务器上通过内部 HTTPS 验证业务；本机 `--local-check` 使用独立 ASGI/SQLite。测试账号通过隔离、不监听网络的正常注册处理器创建；在线注册保持关闭。所有业务使用产品 API，不直接改库制造结果。

上传恢复后：先部署与健康检查，再在 ECS 执行同一段小样及两身份验证；另行记录 PostgreSQL 和远端网络结果。之后再接 Android 录音及自动转写提交，检查实体设备与公网 HTTPS。电脑通过不证明手机任意网络可访问 Groq。

## 原始证据（被 Git 忽略）

- `services/backend/var/client-asr-acceptance/initial.draft.json`
- `services/backend/var/client-asr-acceptance/groq-calls/calls.jsonl`
- `services/backend/var/client-asr-acceptance/product-loop/report.json` 与 `run.log`
- `services/backend/var/client-asr-final-regression.xml`

测试身份文件只在测试运行目录内，未包含于上传包或文档。
