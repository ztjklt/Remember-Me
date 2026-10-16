# 语音等待与安静环境停播排查

2026-10-16，Asia/Singapore。本人反馈普通语音对话倾听／思考很久，回答中途停声，并补充停声时没有开口、周围也比较安静。本轮不能按正常插话解释该现象。

## 修改

服务端源码位于 `/Users/jitian/.codex/worktrees/speaker-introductions/Remember Me`，分支 `codex/voice-continuity-20261016`，提交 `cbf81f6`。主工作区已有未提交的 iOS 和文档修改保持原状。

- 原 Worker 在每个 `user_state_changed: speaking` 事件里直接永久取消回答，跳过了 SDK 的最短打断时间和误打断恢复；当前 manual turn 模式也不会自动处理这些恢复。改为持续语音活动 300 ms 后暂停，安静两秒且没有新识别文字则恢复；实际 ASR final 才替换问题。手动打断、结束、撤权与旧轮晚到保护保留。
- 实时问答继续检索原聊天消息、使用有效缓存摘要和原有证据校验，但不为当前通话额外生成摘要或单独请求表达改写。文字问答保持原路径。此改动减少可选模型调用，不能保证网络或主模型的固定延迟。
- 隔离探针新增 `--uninterrupted`，在麦克风静默时等待整段播放回到 listening；`--complete-playback` 要求三轮场景的末轮也完整播完。不能把最初几帧当成全文播放。

不改公开 Backend Contract、数据库迁移、供应商、地区、长期凭据、采集授权或 Android 实现。没有使用本人声音、声纹或私人聊天做探针。

## 已执行验证

- Backend 完整 `services/backend/.venv/bin/python -m pytest -q`：退出 0；790 项收集，784 项通过、6 项跳过。另有现有 Starlette／SQLite 弃用提示。旧聊天原消息召回、缓存摘要、撤权、资料失效、晚到答案与跨人隔离包含在回归内。
- Worker `services/realtime/.venv/bin/python -m pytest tests -q`：69 项通过，包括噪声／短活动不取消回答、误触发恢复、实际新问题取消旧答和关闭时清理计时器。
- `python3 -m py_compile tools/verification/public_voice_scenario.py` 和 `git diff --check` 通过。
- 原线上版本 `ios-speaker-display-e3a7e24` 的三轮／两种打断／65 秒静默探针本次通过，但该旧场景只验声音开始。原版本另一次无插话整段播放通过，9.629 秒 listening，13.939 秒 question，19.162 秒 answer，25.482 秒回到 listening，416 个非零音频帧。这不能否认本人遇到的间歇故障。
- 修改后本机独立 QA Worker＋原生产 Backend 的单轮无插话整段播放通过，425 个非零帧；临时通话结束、VOICE 撤销、答案精确删除、个人 profile 仍 missing 的检查均通过。
- 初次本机 Worker 注册等待超时，进程已停止。随后两次打断检查使用 600 ms 暂停门槛，未通过原有 1.2 秒宽限断言；其中一次多出 20 个非零帧。未放宽断言，当前门槛已改为 300 ms。
- 300 ms 版本第一次三轮检查在第二轮超时，同时本机 RTC 日志出现信令 ping timeout／重连及识别 APIConnectionError；所有探针资源已清理。没有把这次失败算成通过，也没有证明它是本人手机停播的唯一根因。

## 当前状态

最终 300 ms 版本的三轮／完整播放复核仍未通过：27.185 秒 listening，首轮 33.456 秒 answer；第二段输入后首轮在 44.676 秒回到 listening，47.992 秒收到 ended，没有第二个问题／答案。Worker 汇总只有一个 ASR final，WebSocket close_code 1006，并报 `Realtime recognition stopped: APIConnectionError`。这次不能验证新门槛的完整打断／65 秒／末轮播放；没有通过反复重试或放宽断言将其计为成功。测试通话结束、VOICE 撤销、合成答案清理均通过，本机 QA Worker 已停止。

**本轮代码修正已提交，但尚未发布 Backend 或 Worker，没有重新安装 iOS。** 原线上版本保持不变。完整多轮链路仍存在识别连接中断，根因没有细化到具体网络设备／平台；不能称用户遇到的倾听、思考和安静停播已完全修复。真机安静外放、本人音色及实际延迟尚未验收。

脱敏报告在服务端工作区 `build/voice-continuity-baseline-20261016.json`、`build/voice-uninterrupted-baseline-20261016.json`、`build/voice-uninterrupted-staging-20261016.json`、`build/voice-continuity-final-staging-20261016.json` 和各 `voice-continuity-staging-*-20261016.json`。原始运行日志／控制脚本只在 ignored `build/private/`，不提交凭据或问答文字。
