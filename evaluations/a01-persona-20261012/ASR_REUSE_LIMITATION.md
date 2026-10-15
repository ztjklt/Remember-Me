# Companion 回归的 ASR 调用口径更正

2026-10-12 的原声音补记、v3 回归、v4 回归使用相同不可变 WAV，SHA256 为 `d7c9bf169a2d9e63decd5c1ab5faf889d70061fd8da30531150e78ed7d30527a`。v3/v4 都真实新建了 Backend audio_id，调用转写接口并将实际返回稿原样确认；没有复制创作稿、gold 或通过客户端写入 ASR。

但在 v4 后复核 provider audit 发现，Paraformer adapter 的检查点按 policy 与音频 SHA 定位。相同原音恢复已有 task_id，再向 provider 取任务状态与转写结果，避免重复提交。因此这三次记录的云端 task_id 相同。原先“新 ASR/fresh ASR”的表述不能解释为新云端识别任务或三次独立识别实验；准确表述是**新的 Backend 音频链路，授权重新取回同一真实云端识别任务的结果**。

证据保存在忽略目录中：

- `services/backend/var/a01-20261012/evaluation/asr-paraformer-v1/adapter-state/calls.jsonl`：03:21:58、03:55:31、04:09:14 UTC 的三条同音频记录。
- v3/v4 各自目录的 `asr/provider-task-provenance.json`：按转写操作起止时间匹配该次 provider audit。
- 两轮 `REPORT.md` 追加明确更正，原 run.json、实际 ASR、失败、模型草稿和旧音频都保留。

没有为制造“新识别”而清除云端任务检查点、改动不可变 WAV 或补跑调用。模型回归问题相同，但授权资料版本不同；即使 ASR 文本逐字一致，也不声称整份模型输入完全相同。v3/v4 的回答分别被语义校验拒绝，均未保存答案，也未合成对应答案声音；临时补记随后已撤回。
