# Twin 语音误答“没有数字托付”修正

用户反馈问 Twin 是否有数字托付时回答“没有”，并确认发生在**本人模式语音通话**。本轮依据代码及部署记录诊断，没有读取本人的真实通话或账号资料。

## 原因

最新已部署的054／iOS1.16.1包含数字托付管理和游客暗号保护，见[部署记录](IOS_LATEST_DEVICE_DEPLOYMENT_2026_10_16.md)。但“功能已实现”没有同步到普通对话：AI Core 的 `TwinInput` 只有记忆候选、聊天和表达资料，`CONVERSATION_SYSTEM` 没有产品功能说明；服务端将“有没有数字托付”照常交给模型生成。它可能无依据地否认功能。此前验证覆盖设置、解锁、撤销和竞态，未覆盖这类能力问答。

本人语音的火山回调 `validated_answer` 和原实时语音 `answer` 均调用 `api/twin.py::answer_question(... conversation_mode=True, realtime=True)`，因此该遗漏影响本人语音和文字聊天。

## 本地修正

- `app/twin_capabilities.py` 对明确的数字托付功能／入口／设置请求提供服务端维护的能力说明，指向 iOS 孪生页左上礼物图标“留下数字托付”。说明亲友无需账号、暗号和专属来源的关系及开放条件，提醒在专用界面私下录入暗号，不声称已执行托付。
- 在本人普通会话的共享发布路径使用现有 `CONVERSATION` 答复，`model_version=twin-product-help-v1`，无个人事实证据。保留鉴权、许可、前文、幂等、归档、范围和通话发布检查，不再由模型猜测这类功能问句。
- 完整匹配明确问法，包含个人历史或混合事实的问题仍按原证据问答；不读取／列出已有计划，不创建托付、许可或人物记忆，也不向游客提供本人管理入口。
- 无公共 Contract、数据库迁移、原生界面或供应商变化。此修正只说明功能与入口，尚未实现语音通话中自动打开设置或代为创建托付。

## 验证与发布状态

Backend实际运行，隔离数据库与确定性模型／RTC替身：

1. `pytest -q -o addopts='' tests/test_twin_capabilities.py tests/test_twin_conversation.py tests/test_twin_transport.py tests/test_twin_history.py tests/test_guest_entrustments.py tests/test_volcengine_voice.py tests/test_realtime_voice.py`：**153 passed，2条既有弃用警告，退出0**。
2. 追加真实 Backend 火山回调入口回归后，`pytest -q -o addopts='' tests/test_twin_capabilities.py`：**18 passed，2条既有弃用警告，退出0**。该组与上组有重叠，不合计为171个独立用例。新用例从创建／启动通话到 `/internal/volcengine/calls/{id}/chat/completions`，断言 SSE 返回“支持数字托付”、正常结束标记、心跳回答回执和入口说明，且零模型调用、没有新计划／许可／记忆。也验证旧助手错答、游客隔离、撤权、个人事实和请求幂等。

两组均在 `services/backend` 下通过 `.venv/bin/python -m` 执行。日志 `/tmp/remember-twin-entrustment-awareness.log`、`/tmp/remember-twin-entrustment-voice-proof.log`，副本在 ignored `build/twin-entrustment-help-20261016/`。

**本轮修正尚未部署**，正在使用的054仍可能给出原来的错误回答。没有更换服务器、安装手机或调用真实 RTC／TTS；上述回调测试不能代替本人手机真实通话试听。
