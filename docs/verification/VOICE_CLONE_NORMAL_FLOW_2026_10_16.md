# 声音复刻正式流程修正

2026-10-16，Asia/Singapore。本人澄清本轮目标是先正常跑通声音复刻功能，而不是扩展录音／回听。此前原样本已由本人确认；旧试听被本人评价为不像自己。对照候选仍待本人试听确认，不能当作相似度验收通过。

## 修改

源码提交 `b3292be`，保存在 `codex/volcengine-modular-voice-20261016` 的现有服务端维护工作树，并同步到主目录对应五个文件。

- 正式样本提交继续保存原文件。只有供应商使用的临时副本会解码成有界的 24 kHz 单声道 WAV，低电平人声应用线性增益，目标 RMS 0.05、增益受峰值 0.8 限制；不变调、不变速、不拼接、不加长录音。正常电平样本不额外放大，原有时长／静音／大小限制保留。
- 临时取样仍要求当前有效 VOICE 许可、当前 enrolling 状态、未过期票据。转换后再次检查状态、授权、票据与对象路径，撤权不能在转换期间漏出副本。原文件不被覆盖。
- 当前 CosyVoice v3-flash 及同样支持这些参数的 v3.5 模型使用明确的“不做声音预处理／启用音量归一化／最多使用 15 秒参考”参数；其他模型不误加未声明的参数。没有切换模型或供应商。[参数依据](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api)。
- 当前 profile 按最近一次生成记录决定。替换音色被停用后返回缺失状态，不能重新露出更老的 rejected 音色；旧记录仍供审计与独立许可撤回时清理。
- 本人试听确认与供应商 ready 保持分离，不自动将音色设为 accepted。共享 Contract、数据库 schema、iOS 安装包均不变。

## 已运行检查

- 86 项声音、删除、试听审核与国内通话定向测试通过，包含正式提交参数、供应商 WAV 副本、原音保留、波形／时长不变、静音拒绝、转换时撤权，以及停用新音色不恢复旧音色。
- Backend 全量最终 830 通过、6 跳过；跳过需要独立 PostgreSQL 测试库的项目。最初全量出现一个旧断言：假设删除中的新音色仍会回退到旧音色。已按本轮禁止旧音色复活的语义修正断言，定向及全量复验均通过。首次失败没有记为通过。
- 日志：主目录 ignored `build/volc-research/voice-normal-flow-final-tests-20261016.log` 与 `voice-normal-flow-backend-final-all-20261016.log`。

## 发布与真实供应商检查

CloudBase053 / `ios-voice-normal-flow-b3292be` 发布任务 2375452 已完成，控制面唯一 100% 流量版本和公开 service-info 均核对一致。迁移 head 确认为既有 `0028_voice_approval`，没有执行新迁移；原环境配置和固定 045 运行镜像保持不变，只更新源码及 release ID。052 的镜像与私密配置快照保留，以便应用回退；不删除或回退音色审核记录。

真实供应商实跑使用已有、明确隔离的 `ios-synthetic-demo` QA 账号及系统合成音频，只新建本次 VOICE 许可。没有提交本人原音、没有替本人接受音色，也没有创建电话：

- 正式 `POST .../volcengine/profile` 返回 200，供应商生成成功；后续正式 profile 查询 ready。
- 正式试听接口返回 200、非零 294720-byte PCM，24 kHz 单声道。生成前后正式 review 都为 pending，且试听后出现 previewed_at。
- 存储中的原始上传字节逐字一致；静音／错误票据／撤权期间转换等边界由对应定向测试验证。
- 按精确本次 profile 调用 retry，撤销精确本次临时许可；试听已拒绝访问，独立 SQL 确认临时音色 deleted、原始样本引用与远端 ID 都已清空。
- 首次实跑的试听请求本身已返回 200，但测试把 gateway 合并后的 Cache-Control 误判成必须与 `no-store` 完全相等。实际为 `no-store, no-cache, must-revalidate, max-age=0`。首次临时音色清理已独立核对，修正断言为包含 no-store 后用新的隔离音色重跑，完整链路及清理通过。没有把首次断言失败冒充整条流程通过。

安全证据：主目录 ignored `build/volc-research/voice-normal-flow-public-proof-20261016.json`、`voice-normal-flow-owner-readback-20261016.json`；运维源包、摘要和发布状态在服务端维护工作树 `build/voice-normal-flow-*20261016*`，凭据及原始回执仅留私密目录。

本人此前的音量校正候选继续保留，可在现有 App 的“孪生 → 电话 → 刷新语音服务 → 试听复刻后的音色”试听。本轮证明正式流程可提交、生成并返回可播放的合成音频；**不证明本人觉得声音相似，不把待确认音色自动用于通话。**
