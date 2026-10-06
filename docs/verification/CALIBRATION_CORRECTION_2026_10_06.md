# 本人事实校准修复验证 — 2026-10-06

分支 `feature/ai-agent-core`，继续使用原仓库目录。修复用户校准姓名后再次问身份却返回材料不足的问题。真实个人文本、完整响应和数据库备份仅放在 Git 忽略的 `build/agent-demo/provider-check/`，权限 0600；下述测试使用虚构人物。

## 原因与行为

- 校准比较判为 MODEL_ERROR，但 Persona 将明确更正保存为 CONFLICT，旧身份未被修正。
- 检索把本人 CALIBRATION 作为旧结论的反证排除，Twin 对旧结论的冲突直接拒答，又把矛盾原因改写为材料不足。
- 本人明确纠正事实时更新当前理解，保留未更正事实和对应证据；旧结论 SUPERSEDED，原始 Episode、提取结果和校准锁保持历史。
- 相同问题优先引用最新有效校准，返回 ORIGINAL 与 CALIBRATION 证据；未经授权、失效或被替代的校准不会恢复使用。矛盾拒答保留真实原因。
- 旧转写混有已更正事实时，私有整合 Worker Schema 只允许 SIMULATION / INSUFFICIENT；学校等未更正事实仍可引用原材料，整段旧错误不再被当作当前原话。提示版本为 `agent-workers-v4`。
- 页面区分历史提取结果、当前理解与校准证据；提交完成后清除旧 Twin 回答，提示再次提问，不把历史结果当作更新后的理解。
- 未改变 `packages/contracts`、API 或数据库 schema。维护工具只用于本机 configured 演示数据，默认预览；显式应用会先备份数据库，通过已有授权、证据检查及 revision CAS 追加快照。更晚的校准或版本不匹配会拒绝应用。

## 验证

| 检查 | 结果 |
|---|---|
| AI Core `.venv/bin/python -m pytest tests -q` | 143 passed；相同问题、标点变化、单字问题、最新校准、失效/第三方/撤回材料、情境冲突、事实保留及旧混合原话拒绝 |
| Backend `.venv/bin/python -m pytest tests -q` | 全量回归通过；最后补充的新版校准保护另由当前 Agent 专项覆盖 |
| Backend `.venv/bin/python -m pytest tests/test_agent_loop.py -q` | 当前 22 项通过；预览不落库、应用追加版本、校准和 Episode 不变、旧版本/未完成/跨主体/撤回/新校准保护 |
| `PYTHONPATH=scripts services/backend/.venv/bin/python -m pytest scripts/agent_console/tests/test_server.py -q` | 4 passed |
| Playwright capture / agent 回归 | 通过；实际浏览器录音走 fixture 服务，校准完成后的旧回答被清除，五维比较与同意撤回保持有效 |
| `node --check scripts/agent_console/static/agent.js`、Git diff | 通过；仓库没有为此工具配置独立 lint、format、typecheck |

真实数据在 configured 模式复现：原快照 revision 4，校准为 COMPLETED，比较原因 MODEL_ERROR，问身份返回 INSUFFICIENT / 未解决的矛盾。修复路由后，未改任何数据就能返回有效本人校准原话。

真实供应商 Persona 预览提出 CHANGE / IDENTITY，保留学校与学历。维护工具再次预览通过后，应用为 revision 5；当前身份使用本人更正，旧结论保留为历史，原校准记录、锁定摘要和原始 Episode 结果不变。浏览器验证相同身份问题正确返回 ORIGINAL，姓名另一种问法返回基于校准的 SIMULATION。

最终浏览器实测：“我是谁？”返回本人校准的 ORIGINAL（1 条证据）；“我叫什么名字？”返回 SIMULATION（1 条校准证据）；“我在哪所大学读研？”返回 SIMULATION（2 条证据），保留学校与学历且不带旧误识别。三问均首次成功，恢复原校准的完整响应与修复前一致，当前快照仍为 revision 5。

补充验证发现学校问题曾返回带旧错误的整段原话，因此收紧私有整合 Schema。收紧后曾出现两次 AI Core 502 / Backend 503；增加本次只允许整合的明确 Worker 指令后，真实供应商和最终浏览器验证通过。未放宽证据校验或回退 fixture；初次失败及最终详情分别保存在忽略目录的 `calibration-narrow-schema-initial-failure.json` 与 `calibration-browser-after.json`。

## 操作与边界

升级代码不会自动重写历史快照。确需修复已有派生快照时，从根目录运行：

```bash
services/backend/.venv/bin/python scripts/reapply_agent_calibration.py --calibration-id <已完成的ID> --expected-revision <当前版本>
```

检查私有预览报告后，增加 `--apply` 应用；无需重新上传音频或重复提交旧校准。原校准的 `resulting_revision` 保留当时版本，当前理解会有新 revision。

姓名同音字无法仅靠音频确定汉字；这次验证修复本人更正的反馈路径，没有宣称 ASR 从此不会误识别。真实验证使用用户已有校准，没有替用户填写新答案，也没有放宽来源、授权、情境或原话校验。后续录音和其他事实仍需现场验证。
