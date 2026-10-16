# 第二轮服务端审计：实时交互优先（2026-10-16）

本轮承接 [第一轮数据库超时审计](BACKEND_TIMEOUT_AUDIT_2026_10_16.md)，重点是通话正在进行、用户插话或离开页面时，慢识别、临时问答、后台整理及资源清理会不会拖住实时交互。当前工作区源码已修复；**没有部署 Backend / AI Core，没有提交，也没有改 Contract 或迁移**。现网仍是 054；iOS 1.16.2 的独立安装不包含这些服务端变更。

## 新问题及修复

1. **游客语音仍在事件循环内访问数据库。** 合成每个音频包直接取得 publication lock 并重算范围、来源快照；数据库慢时其他通话和 `/health` 同步停顿。已把游客提问、合成的同步校验放到工作线程，保留每包和最后交付前的授权检查。首次问答、正常重试与临时回答发布返回前明确提交，避免把全局锁留到 HTTP Session 清理。本人 Twin 正常重试和不落库回答也补齐相同的释放边界。

2. **旧指定账号托付的语音问题直接在异步路由中调用同步 Twin。** 一次模型等待就可能堵住整个 Backend。语音提示、身份确认、暗号转写与提问改由同步工作线程处理，播放的初始校验也移出事件循环；原有账号、密语和来源限制保持不变。

3. **SSE 断开会取消清理本身。** `StreamingResponse` 的 AnyIO 取消范围会使 finally 中的 `retire` 无法执行，留下可发布的旧 `active_turn`，后台模型线程可能继续保存晚到答案。已对退役及任务回收做 shield；先持久退役，再收掉等待线程结果的任务，既有 publication guard 拒绝晚到结果。测试实际模拟 ASGI disconnect，重复 5 次，要求释放旧轮次后才能放行迟到的模型结果，且不留下通话答案。另复现了相反的完成边界：客户端收到 stop / DONE 就关闭时，生成器尚未执行完成标记，会误退役已经交付的答案。现在在发终止元数据前设置完成标记，分别验证 stop 和 DONE 后关闭都保留成功回答。

4. **ASR 关闭顺序反了。** 音频泵、文字泵及看门狗原本等上游 WebSocket 关闭握手完成之后才取消，断开后还可能收发、查库。现在先取消并回收三个子任务，再退出上游连接上下文；上游关闭不能再拖着这些任务继续运行。

5. **后台提取占满唯一模型槽，实时回答排队超时。** `/process`、资料整理与 `/twin` 原本共用 semaphore；CloudBase 后台上限为 1 时，一次慢提取会挡住前台回答。新增独立的 `AI_INTERACTIVE_MAX_CONCURRENT_REQUESTS`，默认 2、允许 1–8；原 `AI_MAX_CONCURRENT_REQUESTS` 控制后台 / schema 工作。后台 1 加前台 2，进程最多同时 3 个供应商操作；仍是同一个已选模型，保留原队列等待和错误语义。第二个交互槽允许上一段同步调用尚未完成时接续替换轮次。测试证明前台无需等待受控慢提取结束，且第三个并发前台请求不会突破 2 的上限。

6. **后台声纹整理在全局发布锁中做计算和存储。** 向量提取以及本人原音复制上传都可能占住全局锁，拖慢录音和通话写入。现在先计算有界的声纹向量、准备私有音频副本，再进入短事务重新核验许可、当前声纹身份和任务租约；只有仍匹配本人的段落才发布为人物资料。未引用的准备副本在事务外清理。单段最多准备 8 个说话人，超过预算只跳过后台整理，不阻断通话。上传途中撤销身份的回归要求零本人 Episode、无可引用的准备副本。

7. **TTS 已连接但没有音频时可等到 90 秒。** 连接建立、task-started 不能被当作首音；现在共用 12 秒首音期限，收到音频后包间等待最多 8 秒，连接建立上限 5 秒，整段仍有 90 秒总预算。超时、空完成或异常协议统一进入已有 `REALTIME_UNAVAILABLE`；关闭音频生成器同时释放 WebSocket / HTTP Session。测试分别覆盖首音停滞、播放中停滞、空完成、正常完成和主动关闭。

8. **临时问题原音先读完整 body 再判断 8 MB。** 大请求会先占用额外内存。现在按数据块拒绝超额内容，保持原有 8 MB 业务边界及错误形状；读取前的同步授权检查结束即释放数据库事务，不在上传或 ASR 等待期间占用连接。

## 实际检查

新增回归先在未修复代码上观察到：游客合成慢范围检查使并发 `/health` 超时；首次、重试游客回答仍阻塞独立写入；ASR 进入上游关闭时识别泵尚未取消。对应 4 项均先失败。单独的 ASGI 断开检查也先失败，断开后 `active_turn` 仍为 `ve_0`。

修复后的定向检查包括 171 项游客 / 托付 / 原实时语音回归、28 项国内通话与动态检查、28 项声纹 / 自然采集回归及新的 TTS / 动态组合，均通过。全量快照和真实 PostgreSQL 结果如下；最后的终止标记边界小修另由最终 43 项流回归覆盖：

Backend 全量在共享 canonical 工作区运行，pytest 按导入时点加载源码；本轮没有创建独立源码副本或记录冻结 hash。同期另有任务修改并验证 wearable / voiceprint 等代码，因此该结果是这次运行实际加载的工作区验证，不代表一个不可变提交的认证。最后的 stop / DONE 完成标记修复在全量启动后落地，其两项边界由上述最终 43 项定向补验覆盖。

- Backend 全量：**1021 passed、7 skipped，1032.32 秒，退出码 0**；跳过项是普通环境未配置独立 PostgreSQL 的检查，另由下方真实 PostgreSQL 运行补验。
- AI Core 全量：`uv run pytest -q -o addopts='' --tb=short --show-capture=no --junitxml=/tmp/remember-dynamic-ai-full.xml`，**324 passed，7.48 秒**。
- 独立 PostgreSQL：**28 passed，35.45 秒**；无跳过。
- 最终动态 / TTS / 国内通话：**43 passed，86.59 秒**，包括最后的 stop / DONE 完成边界修复。

Backend 全量命令：

```sh
uv run --extra deployment pytest -q -o addopts='' --tb=short --show-capture=no --maxfail=3 \
  --junitxml=/tmp/remember-dynamic-backend-full.xml
```

独立 PostgreSQL 16 / pgvector v0.8.1、仅监听本机、每个用例独立 schema：

```sh
uv run --extra deployment pytest -q -o addopts='' --tb=short \
  --show-capture=no --maxfail=2 \
  tests/test_postgres_runtime.py tests/test_realtime_responsiveness.py \
  tests/test_realtime_dynamic_priority.py \
  --junitxml=/tmp/remember-dynamic-postgres.xml
```

最终流回归使用 `tests/test_realtime_dynamic_priority.py tests/test_realtime_stream_limits.py tests/test_volcengine_voice.py tests/test_volcengine_features.py`，JUnit 为 `/tmp/remember-dynamic-final-streams.xml`。

完成后重新读取 JUnit 文件核验，四份均为零失败、零错误：

| JUnit 路径 | 总项数 | 跳过 | 文件最后更新时间（UTC+8） |
| --- | ---: | ---: | --- |
| `/tmp/remember-dynamic-backend-full.xml` | 1028 | 7 | 2026-10-16 20:13:46 |
| `/tmp/remember-dynamic-ai-full.xml` | 324 | 0 | 2026-10-16 19:51:20 |
| `/tmp/remember-dynamic-postgres.xml` | 28 | 0 | 2026-10-16 19:57:08 |
| `/tmp/remember-dynamic-final-streams.xml` | 43 | 0 | 2026-10-16 19:59:34 |

Backend 全量 suite 的开始时间为 19:56:33，JUnit 计时 1032.249 秒，与终端结束汇总一致；此前中断运行留下的 340 项文件已由完整结果覆盖，未作为通过依据。四项警告为既有 Starlette / AnyIO / SQLite 弃用提示。

首个分块原音检查使用同步 TestClient，输送层先缓冲全部生成器内容，造成该检查失败；改为真实逐块交付的 HTTPX AsyncClient / ASGITransport 后通过，并重跑上述 PostgreSQL 28 项及最新全量快照。该过程没有放宽 8 MB 限制。

该进程只设置指向 `remember_timeout_audit_test` 的 `REMEMBER_TEST_POSTGRES_URL`，不连接生产数据库。测试集群在命令结束后关闭。自动检查使用合成文字 / 音频和可控 Provider doubles，不调用真实计费模型。

## 验证边界

这些检查证明应用内的并发、期限和取消边界，不能替代真人持续通话、实际运营商网络、声纹准确率或供应商可用性。保留交互槽不抢占已经发出的同步供应商请求，也不能绕过上游限流；超过全部交互容量仍按原有界队列返回忙状态。未引用准备副本采用尽力清理，进程突然退出后的对象存储孤立副本不由本轮证明已经全部消除。

所有新修复尚未部署，现网恢复或客户端更新不能证明这些服务端路径已经改变。
