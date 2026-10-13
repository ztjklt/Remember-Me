# Persona v6：逐点支持性与问题覆盖分开审阅

本轮由用户授权调整审核策略。只改 `services/ai-core` 和本说明；没有修改 Backend、Android、运行数据库，没有启停进程或发出真实云请求。原 18 题及后续真实失败均保留。生成提示为 `persona-conditional-reviewed-v6`，审阅提示为 `persona-semantic-review-v5`，模型和供应商不变。

## 已保存的实际问题

| 真实 trace | 原问题与草稿 | 当时实际结果 |
| --- | --- | --- |
| `2158e043aa7943c49562451ed3c66632` | 复合题；第一点为整段具名补记原文，第二点 UNKNOWN | 两次调用，约 10.10 秒，`incomplete`，502，无答案 |
| `3b9bd0fd8d02407eaca7548944343853` | “亲友这次署名补记的原话是什么？请区分这是谁的记录。”；同一整段具名原文重复两次 | 两次调用，约 6.50 秒，`incomplete`，502，无答案 |

v5 把事实支持性、覆盖遗漏和表达重复装进同一个全答 valid/failure_codes 决策。任何 incomplete 都使全部内容消失。两次历史 reviewer reasoning 未保存，不能补造其理由；保存的草稿足以复现这种全答失败控制流，不足以证明模型具体如何理解遗漏。

## 私有审阅 schema

生成仍使用 FACT / SIMULATION / ATTRIBUTED / UNKNOWN 四种模式，输入及草稿字段不变。审阅请求明确区分本点自身语义完整与另行检查整题覆盖，不把公开输出的默认 coverage/omitted_points 提前传给审阅者。审阅改成一个 JSON 对象，包含：

```json
{
  "points": [
    {
      "point_index": 1,
      "verdict": "supported",
      "codes": [],
      "rationale": "材料短编号及支持范围的简短理由",
      "depends_on": []
    }
  ],
  "coverage": {
    "status": "partial",
    "codes": ["incomplete"],
    "missing_question_parts": ["仍未回答的问题部分"],
    "rationale": "覆盖判断的简短理由"
  }
}
```

每个草稿编号 1..N 必须恰好出现一次。verdict 为 supported / unsupported / uncertain。supported 的 codes 必须为空，其他判定必须有固定错误码；未知字段、漏点、重号、越界、非法依赖或判定与码冲突都明确失败，不猜测补齐。

硬错误码为 `unsupported / names / uncertainty / counterexample / attribution / new_commitment / unsupported_unknown / time / context / not_conditional / style_leak / instructions / irrelevant`。缺少自身必要条件、否定、反例或归属而改变意思，属于硬错误，不能降成“只是没有答全”。

coverage 只允许 `incomplete / redundant`。partial 必须有 incomplete 和非空 missing_question_parts；complete 不得列遗漏。只有重复可以 complete，同时记录 redundant 供质量分析。固定枚举、索引和数量可以进入常规日志，所有自由文本理由仅用于审核或限定的虚构调试记录。

旧私有 `valid/reasoning/failure_codes` 审阅对象不再被接受；这不改变公开问答 API 的旧字段。畸形或失败的模型审阅仍是错误，不提供“默认通过”兼容路径。

## 交付规则与兼容

- 只保留 supported 点，保留原顺序和原文字，不再生成或改写答案。
- depends_on 是额外的删除保护：依赖点被移除时，后续点也递归移除。它不是省略条件或反例的许可。提示明确要求 supported 点自身完整；无法判断独立成立时应 uncertain。
- 从保留点重新计算全部 evidence_ids、understanding_ids、contribution_ids，被删除内容的引用不再交付。
- 所有点被删时返回明确错误。删除了不可靠内容后若仅余 UNKNOWN，也返回错误，不能把程序失败包装成“材料未知”。纯 UNKNOWN 且被审阅支持、没有剔除其他点时仍可交付。
- coverage partial 或任何要点被删除，公开 `coverage=partial`；有实质内容时附固定“部分问题尚未回答。”。不把 question_part、missing_question_parts 或 rationale 自由文本插入正文。纯 UNKNOWN 保留规范未知文字。
- 保留 500 字符总上限，包括作者前缀、引号和固定提示；不足以容纳时明确错误，不截断引文或条件。保留完整支持/反例及 8 条证据上限。生成结构、引用或字面校验失败仍使用原来有界的一次结构修正；本次逐点保留针对语义审阅，不把畸形草稿默认为安全。

公开 PersonaOutput 仅新增两个有默认值的字段：`coverage: "complete" | "partial"`（默认 complete），`omitted_points: 0..4`（默认 0）。omitted_points 是实际剔除的草稿点数，不是未回答问题数；有覆盖遗漏但没删点时可以 partial/0。旧 answer、response_type、各类引用和版本字段不删。纯 UNKNOWN 的支持性不代表生成失败；coverage 是问题处理范围的判断，不是事实真实性或整体质量认证。历史答案未携带的新字段不能作为本轮新审阅证据。

不完整回答即使 HTTP 200 仍应在质量报告记为 partial，不能算完整合格。redundant 不单独使 coverage 降级，但仍是表达质量问题。

## 原文与语义安全

对 ATTRIBUTED，程序在审阅请求中明确 `attribution_label_verified=true`，`quote_match=full/excerpt`。作者/分类来自实际所选补记；正文连续原文匹配在审阅前完成。full 说明与该补记全文相同，模型不再被要求证明它是否是原文，或证明作者叙述的事件在现实中发生。对于原话/记录者问题，完整具名引用可作为有据回答；ASR 原文含糊不等于 AI 改写出了新动作。

这不取消相关性、归属、否定和语义范围审查。摘录仍须对照所选补记全文；不能截掉“并非”“仅一次”等条件，不能以引用形式偷换成本人人格。SIMULATION 必须有直接支持当前问题的确认理解，共享话题不够；名字字面匹配不等于身份相同。正文自足性和模型漏报依赖仍是语义能力限制，不能宣称程序已证明全部保留点独立正确。

## 诊断与预算

既有 `AI_PERSONA_FICTIONAL_DEBUG_TRACE` 默认关闭、仅 development/test 显式允许。启用时新增 `<trace>-semantic_review.json`，保存完整结构化 review（含每点 rationale、coverage 理由与依赖），与生成草稿放在同一个 Git 忽略目录。仍是最多 100 文件、每文件 128 KiB、不覆盖旧文件；不加入请求包、headers 或 keys。该目录只用于已授权的虚构样例，不能当作普通个人材料日志。

常规 `persona_request` 只记录固定判定/码、point_index、删点编号和数量、缺失问题数、coverage。schema 错误仍使用字段路径白名单，不输出自由理由、正文、姓名或未知字段名。

总预算仍是包括共享槽等待的 90 秒，单次请求最多 45 秒，全部最多三次。结构修正与网络超时重试共享预算。逐点审阅只有一次有效判断；不因为否决或 coverage partial 再投票、重问或补写。审核网络超时可在剩余预算内重试，格式错误、语义判定和限流等不作为网络重试。

## 实际运行的离线验证

新增点评审测试初次 **14 failed / 12 passed**，随后实现通过。再增加第三方观察偷换、不相关 trait、依赖不能豁免反例、固定提示不能越过字符上限等对照。复核还以一个失败测试锁定“未审阅输出的默认 coverage 被提前传入审阅”的问题，随后移除该字段并拆清 scope。最终完整 AI suite **406 passed**，69.31 秒，两项既有依赖弃用警告；没有隐藏失败。此前一轮完整 suite 为 405 passed/41.60 秒，上述新改动后重新全测。现有 AI venv 执行 pytest，代理变量仅在测试子进程内清除，没有更改运行环境。

测试覆盖完整具名原文、复合题与错误 UNKNOWN、重复不是硬错误、正确点不因其他点错误消失、引用重算、传递依赖、删后仅余 UNKNOWN、全部失败、完整 schema/索引校验、截断否定、偷换第三方观点、新承诺、无关理解，以及完整理由只入显式启用的虚构文件。

还直接读入上述两份保存草稿，并断言测试 fixture 与历史草稿逐字段一致、补记文字等于当时签名记录，进行无云调用的控制流回放。新审阅是明确标注的离线 fixture，不是历史缺失理由或真实模型新判断。回放结果：simple 在每点 supported/仅 redundant 的 fixture 下返回 complete/0；compound 在原文 supported、UNKNOWN 为 unsupported_unknown 的 fixture 下返回 partial/1 并保留原文。原文、审阅 fixture 和返回值独立保存于 `services/ai-core/var/persona-v6-saved-trace-replay-20261012.json`。

这些测试证明程序如何使用逐点结论，不能证明真实模型会正确作出每个结论，也不能把 v5 的 502 改记为成功。本轮没有真实服务验收。原 18 题 `run.json` SHA256 仍为 `d8a9a902afc233c08f2c17df2deb326b6bea72a83641b7f412e87b1bde652eea`；本轮读取的 v5 run SHA256 为 `54fccd2d9ce168fba12defd8036e93bad1f2517176cdeb99542eb83a9e899a44`。
