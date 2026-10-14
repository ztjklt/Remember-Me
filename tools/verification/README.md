# 实时语音隔离回归

这些工具只用于已有专用合成 QA 空间，不能替本人注册音色、同意采集或确认声音相似度。报告保留事件类型、数字轮次、计数和耗时；不保存音频、问题文字、回答、Actor／Subject 或凭据。既有合成 PCM 和登录材料放在受保护的忽略目录，不提交源码。

## 公开默认声音的完整场景

`public_voice_scenario.py` 走当前 Backend 的公开 default 模式，临时创建专用 VOICE 许可，不修改个人 Profile／供应商预置引用，也不重新发布 Worker 或开启诊断。所用专用账号必须是现有 `ios-synthetic-demo`，Actor／Subject 同受保护的 QA account 文件；当前个人 profile 必须 missing，并检查同一账号没有另一个活跃测试通话。

输入目录包含：0600 的 transport-state.json、既有 qa-question-1.pcm／qa-question-2.pcm（16 kHz、单声道 PCM16），及现有私人 CloudBase control.py／invoke.cjs。QA account 文件也须 0600。工具复用已有 CLOUD_TWIN 许可，不为普通用户创建许可。安装依赖使用 `services/realtime` 的既有环境。

```sh
services/realtime/.venv/bin/python tools/verification/public_voice_scenario.py \
  --private-dir /absolute/path/to/private-fixtures \
  --qa-account /absolute/path/to/private-qa-account.json \
  --report build/public-voice-full-scenario.json \
  --expected-release expected-public-release-id \
  --synthetic-qa
```

执行顺序：公开 service-info 及账号前置检查 → 创建 default ticket → RTC 连接与麦克风发布 → Worker 就绪监听 → 第一次问答及音频 → 第二段合成音频自动插话 → 第二次问答及音频 → 手动打断并核对服务端轮次清空 → 静默65秒 → 第三个独立question／answer事件及新音频 → 核对第二个已保存答案的parent指向第一答案 → 停止本机媒体 → 结束通话 → 撤销本次VOICE → 清理本次合成答案 → 核对持久化结束和个人profile仍missing。

自动打断后至新轮播放、手动打断后至第三段输入，分别核对宽限1.2秒后非零音频帧为0；该窗口是云端传输检查，不是手机实际停播时延。第三轮必须有独立问题事件、答案和新音频，累计capture计数不能单独判通过。

控制面调用运行在独立进程组，25秒超时后结束该组。SQL只用于该Actor／Subject的活跃QA通话计数、当前call证明、已保存parent关系，及当前收到的turn request_id对应的合成答案清理；不会按整个账号或时间窗口删除历史内容。若清理失败，report保留具体步骤和错误类型，整体结果为failed，应先核查这次遗留资源再复跑。程序退出0还要求全部场景和清理通过；进度快照只表明当前阶段。

3719a0b起，语音request_id绑定call_id＋turn_id。探针清理包含本次随机turn对应的旧格式及当前call派生格式，兼容两种已部署版本；仍同时限定Actor／Subject，不扩展至其他通话或历史。语音历史召回限定当前conversation，文字入口保留跨会话检索。

需要独立本机Worker对照时可显式加 `--qa-agent-name`。`rtc_test_dispatch.py` 验证原票据签名、room/call/participant绑定及microphone-only权限，只替换agents中的agentName，保留包括call metadata在内的全部其他字段；原票据的业务授权仍由Backend检查。该能力只用于这个有账号白名单的合成探针，不进入手机代码。注册／停止本机Worker由独立controller完成，不能将本机对照通过称为已发布Cloud Worker通过。

注意：同一QA账号不应同时运行多个探针。控制面授权失效或前置检查失败时不猜测RTC故障；另一个测试call存在时拒绝启动。报告不代表真人音色、耳机路由、手机播放或人格忠实度验收。

## 原有 personal transport 探针

`realtime_voice_probe.py` 保留已批准的隔离预置Profile场景及显式staging dispatch，不改默认真实ticket。仅供专用 `rvp_qa_transport_` fixture；外围controller必须在finally中先清空预置音色引用，再撤销测试VOICE，避免供应商维护误删系统预置音色。不得用于真人Profile。

新增 default 探针不替代该personal路径，也不扩大客户端或公开Contract。两类证据必须分别标明实际运行版本、声音模式、阶段失败和资源清理结果。


## Same-recording spoken introductions

`speaker_recording_probe.py` runs the public capture/process/playback/revoke/delete path with actual ASR and declared synthetic audio. Use a dedicated `speaker_qa_` subject and ignored mode-0600 JSON credentials (`actor_token`, `subject_id`, `other_token`), never a person's existing account or audio. The two system-preset voices must introduce themselves as 小王 and 小李 with the spoken recording/transcription/identification agreement, then make four alternating statements. Names and report fixtures do not replace real ASR evidence. The runner revokes its grant and deletes its original; repeated revocation must preserve the deleted tombstone.

`python speaker_recording_probe.py --origin SERVICE_ORIGIN --private-state PRIVATE_JSON --synthetic-audio QA_WAV --output SAFE_JSON`

The 2026-10-15 production run and limits are recorded in `docs/verification/IOS_SPEAKER_INTRODUCTIONS_2026_10_15.md`. Cross-record recognition and real-person accuracy are not covered by this engineering probe.


`public_voice_scenario.py --natural-capture` 在明确的合成账号、默认声音真实通话中额外核对正常对话原话与麦克风样本采集，并删除本轮资料、样本、答案和许可。短句不需要额外朗读，样本只累积订阅的用户麦克风。当前实际证据见自然采集验证记录；该选项不证明真人音色相似度。
