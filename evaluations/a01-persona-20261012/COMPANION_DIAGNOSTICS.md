# Companion v2 失败记录与 v3 诊断改进

这不是原 18 题的重跑。2026-10-12 后续独立 companion 请求 `a16184a275274998ae80b6e4259d51f7` 在约 36.22 秒返回 502，没有答案。失败原件在忽略目录 `services/backend/var/a01-20261012/voice-companion-live-20261012/run.json` 的 `operations["companion.answer"]`，补记随后按原脚本撤回。

## 现有证据能确定的范围

AI trace `0e82d5a348824297849a9021f55bf223` 显示两次 Weixin JSON 均返回成功，最终 `generation_repair` 抛 `AIOutputInvalid`。没有保存内部 `/persona` 请求、生成草稿或具体本地校验原因，因此不能推断是哪种 schema、引用、姓名或预算错误，也不能恢复错误答案。

可用的签名补记快照为 `asr/signed-contribution.json`，实际 ASR 为 `asr/contribution.json`。原 ASR 写“陈国良”，与主体“陈国梁”字形不同；另有“再问对谁还有用没有，马上扔掉”的断句疑点。它们是需要保留的来源边界，不是已经证明的本次报错原因。没有用 TTS 创作稿改写实际 ASR，也没有通过降低姓名校验绕过问题。

## v3 改动

- 为初稿和唯一一次结构修正各自记录 `persona_validation`，最后请求摘要保留两次 `validation_failures`。日志只含固定类别、白名单 schema 字段路径/错误类型、数值上限和数量，不记录字段输入、正文、姓名、provider key 或请求头。未知字段名统一记录为 `?`。
- 区分来源编号、理解编号、补记编号、姓名不在正文、姓名不在所选来源、错误 UNKNOWN、引用类型、总字符数和总证据数。500 字符上限包含程序添加的作者前缀，8 条证据上限包含已选理解的全部支持和反例，校验都保留。
- 修正生成提示里的字段歧义：ATTRIBUTED 使用恰好一项的 `contribution_ids` 数组，不能新造单数 `contribution_id` 字段。结构修正收到具体且安全的类别/字段元数据，不再只有笼统的 “schema invalid”。仍最多三次调用，修正后必须独立审查；false 不重试、不发布。
- 提示版本为 `persona-conditional-reviewed-v3`。这是一项可诊断性与结构修复反馈改进，不能据离线测试声称已修复上述真实失败。

## 可选虚构草稿记录

`AI_PERSONA_FICTIONAL_DEBUG_TRACE` 默认 false。仅 development/test 允许显式设为 true；用途只限本地已授权的虚构案例，不能用于真实个人材料。运行者需在下一次独立试验启动前显式启用，试验后关闭。

固定写入 `services/ai-core/var/persona-fictional-traces/<trace_id>-<stage>.json`。文件含草稿、阶段和提示版本，不含输入上下文、headers 或 keys。目录经 `git check-ignore` 确认被忽略；最多 100 个文件、每个最多 128 KiB，不覆盖已有记录，达到容量或写入失败不会绕过答案校验。草稿仍可能含虚构材料文字，不要加入版本库。

## 离线验证

新增诊断测试先得到 11 failed，改动后 Persona、诊断和贡献预算相关 58 passed。覆盖白名单日志、敏感字段名清洗、两次失败均保留、姓名字形不能被统一、作者前缀字符数、完整证据数量、默认关闭及环境限制、显式草稿记录、结构修正后语义审查失败不发布。

完整 AI suite 为 **341 passed**，两项现存依赖弃用警告，30.28 秒。测试进程临时清除代理环境变量以避免本机缺失 SOCKS 依赖；没有修改运行时环境。测试没有调用真实 provider，没有重启 AI，也没有改写原 18 题或此次 companion 失败；真实回归须另存新 run。
