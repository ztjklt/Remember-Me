# 原文问答与真实 LLM 校正循环验证 — 2026-10-06

分支 `feature/ai-agent-core`，继续使用原仓库目录。按用户请求审查并简化实验问答路径，
保留现有 Memory 提取和历史结果，不增加压缩、向量检索或新 Memory 框架。
审查与复现见 [Agent loop review](../architecture/AGENT_LOOP_REVIEW_2026_10_06.md)。

## 变更和契约

- Backend 从已授权的 `Episode.transcript` 提供完整原文；Memory 只选择部分 span 或没有
  证据时，原文仍可引用。已有全文证据复用，不改历史 Memory、原始转写或数据库 schema。
- Twin 把原文、当前理解和按时间排序的本人校正分别交给一次 LLM 问答，不再依赖字符
  匹配、身份关键词或全局冲突拦截。程序校验引用和确定回答类型，缺少所问事实时明确说明。
- 供应商输出或证据校验失败返回 502 `AI_SCHEMA_INVALID`；服务暂时不可用仍返回 503。
- 本机 AI Core 已切换为 `deepseek-flash`，使用 JSON mode 和本地 schema 校验；Backend
  ASR 仍使用千问。密钥仅在忽略的 `.env`，不进入 Git 或浏览器。
- `packages/contracts`、Android、Memory 提取实现和存储 schema 均未修改。回答锁定、
  revision CAS、Actor/Subject 隔离及撤回校验保留。未 push 或创建 PR。

## 自动化回归

| 命令 / 验证 | 结果 |
| --- | --- |
| `services/ai-core/.venv/bin/python -m pytest services/ai-core/tests -q` | 147 passed；覆盖全材料问答、无答案、非法引用、校正上下文和 provider 格式 |
| `services/backend/.venv/bin/python -m pytest services/backend/tests/test_agent_loop.py services/backend/tests/test_agent_client.py -q` | 29 passed；覆盖完整原文、锁定、校正、隔离、撤回、CAS 和错误映射 |
| Playwright `scripts/agent_console/tests/browser_capture.py` | 通过；模拟麦克风上传、同意门槛、异步处理、幂等和会话切换 |
| Playwright `scripts/agent_console/tests/browser_agent.py` | 通过；同一回答先锁后答、刷新恢复、五维比较、revision 更新、再次提问、采集建议和撤回 |
| AI Core 目录 `uv build --wheel` / `.venv/bin/python scripts/check_wheel.py` | 通过；独立 wheel 包含 fixture，提取和 HTTP smoke 成功 |
| `git diff --cached --check` | 每次提交前通过 |

浏览器回归使用 `--serve --mode fixture --backend-port 8001 --ai-port 8101 --stt-port 8201`，
按 capture → agent 顺序执行。Playwright 位于 `/tmp/remember-console-venv`，Chromium
通过 `REMEMBER_CHROMIUM_PATH` 指向本机缓存，无新增服务依赖。测试服务已停止。
仓库未配置独立 lint、format 或 typecheck；pytest 有两条既有依赖弃用警告，无测试失败。
打包 smoke 初次失败于脚本仍指定旧 v2 prompt；单独修正为导入当前实现版本后通过，
未修改生产 Memory 提取逻辑。

## 真实 DeepSeek 问答

使用用户已授权的现有材料与 revision 6，实际调用供应商，未注入预期答案。
一次 11 请求的检查包括：同一团队人数/专业问题重复五次、不同措辞、学历构成、
已校正姓名、研究方向、学校，以及材料未提供的队友姓名。

- 五次团队问题和改述均回答团队总共四位组员及对应专业构成，不把总人数误称为四位
  除本人以外的队友。事实一致，措辞可以变化。
- 当前姓名采用本人校正；研究方向和学校有原文依据。
- 未知队友姓名返回 `INSUFFICIENT`，无冒用背景材料的答案引用。

重启 configured 服务后，再通过浏览器实际点击“提问”验证五个请求：团队问题连续三次、
当前姓名、未知队友姓名。全部成功，回答标记为 DeepSeek，每次页面显示与保存的 LOCKED
回答相同，理解 revision 未变化，没有 503 或浏览器脚本错误。未向用户会话提交虚构校正。

个人原文、回答和断言结果仅保存在忽略的 `build/agent-demo/provider-check/`，权限 0600：
`deepseek-qa.json`、`deepseek-browser-qa.json`。重构前的五次 502、早期姓名和未知事实
失败报告也保留在该本地目录，未以成功报告覆盖失败记录。

## 真实 LLM 更新循环

独立临时数据库与合成 Subject，固定 STT 文本，Memory、Persona、Twin、Compare 均实际
调用 DeepSeek。测试结束清理临时数据库，没有更改用户的理解或 Memory。

1. 原文“我们团队一共六人，三人学物理，两人学设计，一人学计算机。”经真实提取与摘要，
   保存 revision 1；提问人数，模型回答六人，并保存答案锁定。
2. 本人校正“我更正刚才的人数：我们团队一共五人，两人物理、两人设计、一人计算机。”
   经真实五维比较和 Persona 更新，生成 revision 2。
3. 再问人数与专业，回答五人、两人物理、两人设计、一人计算机，并引用 CALIBRATION。
   校正前锁定答案保持不变；Episode 提取结果 JSON 在校正前后完全相同。

HTTP 和应用断言全部通过，报告为 `deepseek-real-model-loop.json`，仅在本地忽略目录。
这验证真实 LLM 的“提取理解 → 提问 → 本人校正 → 更新理解 → 再问”循环；
STT 为固定合成输入，不能当作本次现场录音或真实 ASR 验收。

## 运行与边界

本机 configured 服务已重启，访问 `http://localhost:8000/debug/agent/`，刷新并加载本地会话。
仍用 `services/backend/.venv/bin/python scripts/run_agent_demo.py --serve` 启动；有实例运行时
直接使用页面。DeepSeek 的 JSON mode 配置见 [联调文档](../architecture/AGENT_CORE_LOOP.md)。

本次未重新测试耳机现场录音或 ASR，没有验证任意问题都能答对。当前保留全文，达到既有
上下文上限时明确失败，不自动压缩或截断。真实模型即使温度为 0 也可能变化；以上是已测
事实与流程的结果，不是长期稳定性或人格复刻质量结论。
