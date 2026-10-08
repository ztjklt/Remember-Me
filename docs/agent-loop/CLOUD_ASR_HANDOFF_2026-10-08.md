# 云端转写接力交付（2026-10-08）

## 当前结果

已实现独立云端 ASR 适配、网页/Android 明示原音云端处理同意、原始转写与简体
核对稿分存，以及独立三人物全链路验证入口。现有 30 段音频和旧 Whisper 转写
未覆盖。工作台已切到 relay 模式，8878 本地 Whisper 服务已停止；真实文字服务
仍由已有微信 Deepseek-v4-flash 提供。

**本次尚无新增云端 ASR 成功样本，不能宣布产品全流程验收完成。** 用户附件记录
了 `codestral-2508`、`mistral-code-fim-latest` 各一个 8 秒成功样本，但未提供这套
中转的完整端点、凭据位置或实际成功请求体。当前项目未找到该连接；已询问用户。
此前提供的微信与小米密钥不是这套 ASR 中转密钥，不会串用。

## 本轮改动

- `stt_backend=relay`：两个指定入口白名单，显式完整 HTTPS 地址，密钥仅服务端；
  `audio_url`/`input_audio` 格式可配置，尚需在实际中转验证。无自动换模型、换服务商、
  本地模型或 fixture 回退。现有 `http` 适配器作为原部署兼容项保留。
- 启动器本轮使用 relay；旧 `.env` 的 `http`/`fake` 不能意外继承。只有显式
  `http` 加 `REMEMBER_START_LOCAL_STT=true` 才启动旧本地侧车，当前未启用。
- 上传同意绑定端点、模型、请求格式和提示词版本；服务端生成同意记录。旧队列
  不会因服务切换自动外发。后台排队之后、真正发送之前重新查所有者和有效授权。
- 未知/未配置目的地拒绝上传；网页可下载原音，Android 保留本机文件。
- 共用文件锁串行调用，两次完成之间至少 35 秒；429 冷却 305 秒。调用本身不重试，
  沿用任务最多三次的上限；请求错误正文、密钥和音频 base64 不进入日志。
- 200 不代表成功：空输出、截断、结构错误、显式 refusal、常见中英文/简繁体拒绝
  都失败。拒绝启发式不能穷尽自然语言，忠实程度仍需要真实样本核验。
- 每次真实请求记录端点、请求/响应模型、prompt 版本、音频哈希、耗时、状态、usage
  和校验结果。服务报告的模型名称不证明其底层实际型号。
- 新验证脚本新建人物空间与 Episode，复用不可变合成音频，不读取创作脚本/gold
  作为模型输入，也不将旧 Whisper 输出伪称新云端 ASR。
- 后半段问答、分享、撤权和人物任务按步骤保存 checkpoint。响应丢失的 POST
  标记待核查，不盲目再发；已成功的 QA/人物 job 恢复时不重建。

## 接续运行

工作目录 `D:/codex_work/remember-me-agent-loop`，分支 `codex/agent-integration`。
服务端忽略文件 `services/backend/.env` 配置：

```text
REMEMBER_STT_BACKEND=relay
REMEMBER_START_LOCAL_STT=false
REMEMBER_RELAY_ASR_URL=<完整的实际中转 HTTPS chat/completions 地址>
REMEMBER_RELAY_ASR_API_KEY=<这套 ASR 中转自己的密钥>
REMEMBER_RELAY_ASR_MODEL=codestral-2508
REMEMBER_RELAY_ASR_FORMAT=audio_url
```

另一指定入口为 `mistral-code-fim-latest`，只能明确手动选择。协议格式与模型切换
会改变上传同意 policy，不会悄悄沿用旧授权。配置完重启 `services/backend/run_workbench.py`。
所有脚本使用 `D:/codex_work/remember-me-review/verification-venv/Scripts/python.exe`。

```powershell
# 每条只有一次真实请求，共享后端限流锁；只提交实际 WAV 字节。
python tools/monthly_eval/cloud_asr_probe.py --model codestral-2508 --seconds 8
python tools/monthly_eval/cloud_asr_probe.py --model mistral-code-fim-latest --seconds 8
# 短样本确认可用后补 20 秒，再进行三个完整第一段（约 3–5 分钟）。
python tools/monthly_eval/cloud_asr_samples.py --run relay-first --execute
```

三人物操作顺序：音频导入 → 云端 ASR → 保存原始 ASR → 用户此前授权的虚构素材
技术确认（不是人工听读）→ DeepSeek 提取保存 → 原音下载哈希与逐字引文检查 →
所有者问答/未知问题 → 读者授权问答 → 撤权后原音和旧答案不可访问 → 人物候选。

原音哈希可证明来源下载未变，不能证明扬声器播放质量。合成数据、人工听读、
真实手机麦克风、模型语义质量是不同验收项。

## 运行状态和回归证据

- 工作台 capabilities 实际返回 `stt=relay`、`stt_configured=false`、
  `ai_available=true`；旧故事接口 200（抽查一个空间 10 段）。
- 8877/8879 在监听，8878 无监听，无 local_stt/Whisper 进程。
- 两个新命令预检均明确报告配置缺失，未发出请求、未创建测试身份。
- Android APK 已构建并在 emulator-5554 安装启动；这不是新云端录音闭环验收。
- 最终 Python 后端与评测工具 **347 项通过**（0 failures / 0 errors），Android
  **33 项通过**且 APK 构建成功，网页交互与映射 **5 项通过**。均为确定性回归，
  不含新中转的真实模型效果验收。
- 测试日志：`services/backend/var/cloud-asr-final-tests.log`、同名 XML，
  `cloud-asr-android-final.log`。运行文件保存在被忽略的 var 下。
- 一次独立代码审查提出三项重要问题，均已先复现失败再修复：旧配置误选 STT、
  常见拒绝回复被保存、后半段模型调用恢复时重复。补测了同意 policy 在网页异步
  刷新中变化的竞争条件、未配置目的地不得同意上传。旧“本机转写”状态提示已统一。

## 实施判断与限制

- 采用 `audio_url`/`input_audio` 可配置协议，不推测中转地址；代价是实际协议仍待
  补齐连接后验证，两路配置不会自动轮换。
- 利用既有 multipart metadata 保存按次同意 receipt，不增加数据库迁移；旧客户端
  缺少该字段会明确失败，不能绕过云端原音授权。iOS 本轮不改客户端接线。
- 自由文本中的拒绝与本人恰巧说出的同一句话无法仅靠正则完美区分；当前仅拦截
  常见拒绝和结构化 refusal。真实听读、长样本、60 问及手机闭环继续标待验证。

## 尚未完成

1. 补齐实际中转连接并验证请求格式、短/长录音和识别质量。
2. 真正执行三人物新 ASR 全流程，逐项看事实、来源、否定和年份；不能只看 200。
3. 长样本通过后才对 30 段月度材料重新排期；新修订应关联新 Episode 的真实 ID，
   不复用旧 nightly_ingest 的硬编码记忆 ID，也不以旧 60 问结果充当新结果。
4. Android 新流程的实际录音/播放及真人听读，iOS 编译/设备验证仍单列待测。

没有推送、合并或发布。旧数据、音频、失败历史均保留在原工作区。
