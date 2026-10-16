# 游客暗号托付审查问题修复（2026-10-16）

用户在[追加审查](GUEST_ENTRUSTMENT_AUDIT_2026_10_16.md)后明确要求“修复这个问题”。本记录仅描述本地代码、隔离服务测试和模拟器验证；未部署服务器，未安装或验证本人实体手机。

## 已修复行为

- 限流是匹配前的边界。封锁中的正确、错误、短句、显式暗号统一返回固定控制答复，不做 HMAC、scrypt、STT 或普通 Twin 调用；设备重新进入不会清除限制。
- 自然句中完整暗号通过独立密钥 HMAC 指纹定位，唯一命中后才核验原慢哈希，前后有寒暄也不进入普通模型、响应原句或临时聊天。多个完整暗号拒绝，不拼接多个亲友范围。
- 公开／其他托付来源与新暗号做双向检查。来源扫描包括原始转写、核对全文、补充、Memory／Evidence、递归元数据，以及实际会发给 Twin 的时间背景和修订时间。缺少原始转写的原音不视为已安全扫描。发布、进入、状态、花园、原音、问答和声音发布路径均有保护；旧数据或范围中已有披露也不能继续读取。
- iOS 上锁开始即清内容、停录音与播放并废弃在途请求，锁定期间禁止刷新和互动；DELETE 后还需确认公共范围，失败则结束本机会话。文字、语音和上锁绑定调用起点 `X-Guest-Scope-Version`，较早发出、较晚上服务端的暗号请求也不能重新解锁。
- 游客录音与播放互斥，覆盖麦克风权限等待、首／末次授权核验和音频下载窗口。
- 包含具体经历的“我喜欢…”句子可作为候选暗号；真正的泛泛喜好仍拒绝。重复设置相同照护人幂等，保留 active／suspended 状态、核验历史、冻结 baseline 和既有访问；更换照护人仍受原限制。

## 兼容与配置

新增迁移 `0031_guest_secret_index` 仅增加 nullable 检测元数据，保留旧0030计划、scrypt、来源、许可、条件和版本；数据库不存明文或无密钥快速哈希。独立密钥来自 `REMEMBER_GUEST_ENTRUSTMENT_INDEX_KEY`，不进入客户端或模型。本机忽略提交的 `.env` 已配置独立随机密钥，权限0600；验证时只输出配置是否有效，未打印密钥。

旧计划／密钥轮换后，owner 元数据 `secret_confirmation_required` 提示本人重新私下输入或本机离线录入**原暗号**。专用 `POST /api/v1/guest-entrustments/{id}/secret-index` 仅重建检测索引，不改变授权范围或期限。有效计划尚未全部恢复时安全拒绝访客资料访问；密钥失配时状态查询也拒绝，客户端清除缓存并停播放。索引恢复界面会在提交、取消、后台和账号变化时清空输入，忽略旧响应。

撤销后凭据不再能解锁。当前密钥的撤销索引仍可脱敏；已撤销且丢失索引的旧暗号不能从慢哈希反推，可能进入普通聊天，不永久阻塞其他计划恢复。不同托付应采用彼此独立的细节，不把旧长暗号的一部分另作新暗号。机器转写无法证明原音没有漏听，来源仍须本人完整试听；此轮没有声称完成长期跨设备 Legacy 或自动身后判定。详见[兼容协议追加说明](../architecture/guest-entrustment-contract-2026-10-16.md)。

## 实际验证

- Contract：`cd packages/contracts && npm test`，**60项通过**。
- iOS：Xcode27／iOS27专用 iPhone18 Pro 模拟器，实际构建和执行 `ECSConnectionTests`、`EntrustmentDraftTests`、`GuestAccessTests`，**94项通过**（48＋20＋26）；`GuestAccessUITests`、`EntrustmentUITests` **3项通过**，含同一引导的浅色／深色检查。最终 `TEST SUCCEEDED`，退出0。
- iOS 新回归涵盖 DELETE 尚未处理时本机锁定、六类晚到结果、锁定失败、权限中与录音中互斥、播放三个异步窗口、旧暗号请求在锁定后才处理、初次核验后不升级旧请求，以及旧托付重核验成功／失败／取消／错计划等边界。音频回归使用可控录音器和播放器，不据此推断实体手机声学表现。
- Backend 最终定向：`cd services/backend && .venv/bin/python -m pytest -q tests/test_guest_entrustments.py tests/test_guest_access.py tests/test_migrations.py tests/test_entrustments.py`，**126项通过、退出0**，两条既有Starlette／AnyIO弃用警告。该运行在最后的元数据／时间背景修正后启动，使用隔离数据库、虚构暗号和确定性模型／音频替身，不调用真实供应商。
- Backend 全量：`.venv/bin/python -m pytest -q`，**951项通过、6项跳过、4条既有警告，退出0**。此进程在最后的时间背景扫描补强前启动（当时957项）；补强新增2项后总收集959项，最终126项定向已在最后版本全部通过。没有把旧进程当作新增用例已经执行的证据。
- 独立复核额外发现“索引失配时状态仍认可缓存”和“时间背景漏扫”并完成修复后探针复验：`PYTHONPATH=.:tests uv run pytest -q /tmp/remember-guest-review.mJJ3da/test_active_index_read_probe.py /tmp/remember-guest-review.mJJ3da/test_time_context_source_probe.py`，**2 passed，退出0**。分别断言轮换密钥后状态／花园409，以及另一计划的时间背景含暗号时新建422且没有模型调用。材料构造链已核对到 TwinClient，未发现新的有效／未来计划绕过。

日志、探针及截图保存在忽略提交的 `build/guest-entrustment-fix-20261016/`；iOS原始结果 `/tmp/remember-entrust-fix-20261016.xcresult`。本次临时模拟器在测试结束后已关机并删除，不操作其他会话的模拟器。既有未相关工作区改动保持原样，未提交、推送或部署。
