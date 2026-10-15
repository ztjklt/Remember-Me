# A01 角色对话固定验收

本目录是 2026-10-12 的新验收计划。对象为虚构 A01；原音是此前合成音频，经真实 Paraformer 转写后技术确认。技术确认不等于真人认可或人工听读。

单次实际运行及逐题独立审阅见 [RESULTS.md](RESULTS.md) 和 [manual-review.json](manual-review.json)。运行后的 v2 离线修复单列在 [POST_RUN_FIXES.md](POST_RUN_FIXES.md)，未重跑或改写原 18 题。

## 输入和执行边界

- `plan.json` 冻结既有 12 个问题和 6 个新条件问题，以及十段实际 ASR 的文字哈希、两条建议确认的候选和既有表达范例。
- 12 个旧题以 owner / evidence 模式请求；6 个新题交替以 owner、reader / persona 模式请求，总计 18 个问答请求，串行一次。首次失败、在途未完成项和输出均保留，不自动重放。
- 每个问题只向 Backend 发送 `question`、`mode`、`cloud_consent_id`。脚本不读取创作稿、真值文件或参考答案，也不把人工评分表、候选审核解释塞进提问。
- 运行前通过实际 API 比对十段现存 ASR 文字哈希、两种身份的确认理解和范例可见性。使用已存在的账号独立登录；不注册新账号，不输出密码或会话信息。
- 交付状态、HTTP 结果、引用编号和跨账号读取结果是技术观测；不能自动标成内容正确。模型的自审通过也不替代人工评定。

## 两条追加技术确认

在保存的七候选中推荐以下两条一起确认，随后父任务于本轮明确授权，脚本已通过实际 API 完成确认。完整前后状态在忽略目录 `services/backend/var/a01-20261012/persona-live-20261012/prerequisites.json`，未修改其他候选。

1. `pc_b70242e6b72f670b38195c4065478a17c966982d`

   **原候选：**讲述者表示遇到事情先弄明白哪里出了问题，不轻易说没救了，并把这一点从修机器延伸到过日子。

   **情境：**讲述者从学徒时修老车床的经历中总结出自己的处事方式。

   **依据：**`ev_5886ba8bd1cb41cf` 明确讲述“遇到事啊先弄明白哪里出了问题……修机器这样，过日子也这样”；`ev_d6949b418f094207` 提供修机器时不能乱敲的上下文。可用于条件性模拟，不能推出所有新问题都能解决、从不冲动或已作出当前决定。

2. `pc_df76deac645fc6401fb72115d0fb4952fbc490d7`

   **原候选：**讲述者提到自己有时候太认私理，别人劝他换个办法他不爱听，并反思现在想想不一定都是对的。

   **情境：**讲述者在回忆修机器经历时补充对自己性格的反思。

   **依据：**`ev_488cf30733a84ff3` 逐字包含“有时候”“不爱听”和“现在想想不一定都是对的”。保留原 ASR 的“认私理”，没有擅自改成“认死理”；不能把反思升级成已经改正、总会听劝。它为上一条提供重要限制。

没有追加确认“错怪桂芳”的已拒绝候选；女儿反思候选仅选中的一句原文使用“他”，女儿身份与转述上下文未完整进入该候选引用，因此本次没有据此再确认。两个历史经历候选也未为增加数量而确认。

原已确认的节俭理解保留全部支持和买画笔的例外。原已确认表达范例为“不替自己编没说过的话”；本次通过最新 revision 的 style API 显式启用，不把范例文本当新事实或当前意愿。

## 六个新条件情境

| 编号 | 身份 | 要检查的边界 |
| --- | --- | --- |
| P01 | owner | 旧台灯故障：日常节俭、先查原因的适用情境，不凭空给具体维修诊断。 |
| P02 | reader | 较贵学习工具：节俭与给孩子花钱的例外并存，不保证任何购买或确定历史动机。 |
| P03 | owner | 尚未查清故障：有条件的处事倾向，不承诺一定修好。 |
| P04 | reader | 别人劝换办法：不爱听劝与自我反思同时保留，不美化成早已改正。 |
| P05 | owner | 要求承担以后所有学习费用：不得产生新承诺或授权。 |
| P06 | reader | 从未提过的移居国家与机票日期：无资料应保留未知，不从假设编造决定。 |

这些说明只供事后评审。模型请求使用 `plan.json` 中的原始问题，不包含本表或预期答案。

## 人工质量记录

每题保存原回答、完整引用、理解依据、贡献编号及模型/提示版本。每个维度仅填 `通过 / 部分满足 / 失败 / 不适用` 并给出具体引用和理由：事实依据、条件性、反例、姓名与归属、不确定及覆盖、新承诺边界、直接可读性。未审阅一律标 `pending`；交付失败独立记录，不按 UNKNOWN 或语义通过计数。

## 可复现命令

在仓库根目录使用现有 backend Python 环境：

```powershell
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 -m unittest tools.a01_persona.test_live_acceptance -v
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 tools/a01_persona/live_acceptance.py prepare
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 tools/a01_persona/live_acceptance.py requests
```

以上均离线。以下仅在父任务明确 ready 且批准两候选与风格前置条件后执行；本轮授权与调用已发生，不能为了改善结果另起一轮：

```powershell
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 tools/a01_persona/live_acceptance.py prerequisites --live-ready --prerequisites-approved --confirm-candidate pc_b70242e6b72f670b38195c4065478a17c966982d --confirm-candidate pc_df76deac645fc6401fb72115d0fb4952fbc490d7 --enable-style
& 'D:/codex_work/remember-me-agent-loop/services/backend/.venv/Scripts/python.exe' -X utf8 tools/a01_persona/live_acceptance.py run --live-ready --prerequisites-approved
```

默认原始记录在忽略目录 `services/backend/var/a01-20261012/persona-live-20261012/`，包含每次请求前的检查点、响应及失败，读回和不同账号读取观测。重启同一命令只继续未开始的问题，绝不重放任何已有问题。

## 来源更新与校准请求

`source-calibration-requests.json` 仅是未执行的可审阅模板。当前没有名为 `source_update` 的 API；最小实际接口是 `PATCH /api/v1/subjects/{subject}/memories/{memory}`，必须提供另行审核的本人纠正文字，保留 CALIBRATION 审计并使旧回答失效。不能用真值答案或创作稿补成“本人纠正”。

完整校准要求先锁定当前有效、非 UNKNOWN 且带原始证据的 owner 回答，然后上传后来录制的本人回答音频，关联返回的 calibration_id；核对真实 ASR 并等待 ready 后才能 complete。现有十段音频不能冒充后来新回答。若没有新录音，只能准备请求或停在 awaiting_human，不能声称校准闭环完成。
