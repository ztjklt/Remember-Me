# 浏览器 Agent 调试台验证 — 2026-10-05

分支 `feature/ai-agent-core`，继续使用原仓库目录，无新增工作树。目的：在电脑浏览器中使用耳机麦克风调试 Agent，复用现有 Backend / ASR / AI Core，降低 USB 和 APK 构建带来的迭代成本。操作步骤见 [调试台 README](../../scripts/agent_console/README.md)。

## 范围与契约

- 新增 demo 启动器挂载的 `/debug/agent/`，包含麦克风选择、MediaRecorder、试听、音频导入、同意、异步状态、记忆、理解和原文查看。
- 问答、锁定、刷新后恢复锁定、本人答案五维比较、下一次问题和撤回同意均调用现有实验 API。
- 供应商 Key 仍在服务端 `.env`；页面只加载本机演示 Actor 凭据，不写入浏览器持久存储。会话切换清除结果与录音。调试页面拒绝外部 Host / Origin，设置 no-store 与 CSP；正常 `app.main:app` 未新增会话文件入口。
- `packages/contracts`、数据库 schema 和 Android 代码均未更改。浏览器上传使用既有 `IMPORT`。没有发布 APK、建立更新渠道或 push。
- 真实重复录音暴露了 Persona SUPPORT 改写情境的问题，单独修复提示并升级 `agent-workers-v2`；要求逐字复用原 context，保留既有证据与情境校验。

## 自动化与本地运行

| 验证 | 结果 |
|---|---|
| demo 页面 / 会话端点 pytest | 4 passed；字段筛选、禁缓存、外部 Host / Origin 拒绝、缺少会话明确失败 |
| AI Core 全量 pytest | 131 passed；新增同情境 SUPPORT 与改写情境拒绝回归 |
| Playwright `browser_capture.py` | 通过；模拟麦克风实际生成 WebM，经 fixture HTTP 服务处理；验证同意门槛、重复上传幂等和会话清空 |
| Playwright `browser_agent.py` | 通过；Twin 原文、先锁后答、刷新恢复摘要、五维比较、revision 增长、下次问题和撤回清空 |
| 既有一次性 CLI fixture 闭环 | 通过；Memory → revision 1 → ORIGINAL → LOCKED → 五维 → revision 2 → 下一次采集 → revision 3 |
| Windows → WSL localhost 页面访问 | Windows PowerShell 实际请求 `http://localhost:8000/debug/agent/` 返回 HTTP 200 |
| JavaScript 语法 / Python 编译 / Git diff | 两个 JS module 的 `node --check`、Python compileall、`git diff --check` 通过 |

浏览器测试的 Playwright 安装在 `/tmp/remember-console-venv`，使用本机缓存 Chromium，没有新增服务运行依赖或锁文件。仓库未为这个工具配置独立 lint、format、typecheck。pytest 的两条 Starlette / anyio 弃用警告来自既有依赖，测试没有失败。

## 真实供应商

输入是此前已同意上传的实际自我介绍录音，重放为 Chromium 的麦克风输入；页面的 MediaRecorder 再生成 `audio/webm;codecs=opus`，经同意和上传按钮发送到 configured Backend。没有向 Worker 注入转写或记忆结果。ASR 使用 `qwen-audio-3.0-asr-flash`，文本 Worker 使用 `qwen3.8-flash`。

最初完整录音处理在 Persona 阶段失败，原快照保持 revision 1。进一步直接调用同一结构化请求，确认模型改写了 SUPPORT 的情境，被 `Different contexts must remain separate traits` 校验拒绝。补充提示后，相同请求通过；重启服务后重新经过浏览器录音与上传，生成 5 条 Memory、3 条 Trait，revision 1 → 2，处理约 33 秒。此时单次处理未触发重试，不代表延迟或稳定性基准。

在浏览器恢复该 Episode 后，实际点击 Twin 分别询问“我是谁？”和“我的研究方向是什么？”，两次均首次成功，返回 ORIGINAL 和授权原文证据。没有放宽原文校验或使用 fixture 结果。

真实个人原文及详细结果只保存在忽略的 `build/agent-demo/provider-check/`，报告权限 0600；不纳入 Git。初次失败记录保留在 `browser-initial-failure.json`，后续结果在 `browser-loop.json`。

## 验收边界

真实音频传输、转写与理解更新已验证，但输入是已有录音重放，尚未实测用户当前耳机设备或在 Windows 浏览器现场新录一段。本人答案没有替用户编造或提交到真实会话；锁定、五维校准及下一次采集的完整状态循环由 fixture 验证。

麦克风采集需要电脑浏览器权限和 localhost / HTTPS。Android 仍是产品客户端，手机无线调试与安装包分发见 [联调说明](../architecture/AGENT_CORE_LOOP.md)。姓名同音字、长录音证据粒度与真实模型稳定性仍需现场验证。失败会显示真实错误，不自动回退到固定句；失败 Episode 达到服务端重试上限后保留失败状态，可重新录音创建新 Episode。
