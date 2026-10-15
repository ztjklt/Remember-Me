# A01 声音、补记、留言的本地验收

`voice_companion_live.py` 默认只准备。全部真实响应、原音、实际 ASR、失败记录保存在被 Git 忽略的 `services/backend/var/a01-20261012/voice-companion-live-20261012/`。不注册新账户、不修改数据库、不上传 Episode、不切换服务商。

```powershell
python -X utf8 tools/a01_persona/voice_companion_live.py prepare --answer-case P01 --answer-case P04
python -X utf8 tools/a01_persona/voice_companion_live.py status
```

父任务确认 18 题已结束、0020 迁移及本地重启完成，且授权真实调用后，分阶段执行：

```powershell
python -X utf8 tools/a01_persona/voice_companion_live.py run --stage voices --live-ready
python -X utf8 tools/a01_persona/voice_companion_live.py run --stage materials --live-ready
python -X utf8 tools/a01_persona/voice_companion_live.py run --stage companion --live-ready
python -X utf8 tools/a01_persona/voice_companion_live.py run --stage letter --live-ready
```

读者默认读取既有私密账户文件的 reader；可传 `--reader-username` 校验配置，不输出用户名、密码、会话或 API key。只接受固定本地 8891 服务。P02 本轮未成功，不得当成已有答案。

- voices：先对成功的 owner/reader 保存答案读回。已过期时保留旧状态并同题重新提问；不修数据库。开通服务器 A01 音色、独立声音授权，调用保存答案的 speech，验证 WAV 和另一 actor 的拒绝访问。
- materials：串行调用既有 `speech_pipeline.synthesize`，生成独立虚构女性亲友的补记和 A01 同音色的新留言。helper 原有最多三次临时故障重试逐条留在 `provider/calls.jsonl`，不当作不同成功试验。
- companion：上传亲友原音，Paraformer 转写。保存 `raw_transcript_text`、简体 `transcript_text`、独立 `reviewed_text`；技术确认只取实际展示稿，不能从 scripts/gold 补字。署名补记由 owner 接受、双方各自允许模型使用，验证回答引用 ID 与作者姓名，然后生成该回答声音并撤回补记，检查原音、旧答案及缓存声音均不再可用。
- letter：新专用音频上传、实际 ASR 技术确认、owner 发布给指定 reader，验证发布前 reader 不可读、发布后音频字节与原音一致。

`scripts/followup.txt` 是父任务预设的本轮虚构追加原稿，不属于用户原 DOCX；常规四阶段不会生成 followup.wav，也不会把该原稿送入 Twin。必须等父任务实际锁定校准回答后另行授权收集新音频。

阶段与每个 API/外部 TTS 操作都会先写 started。失败或中断后，不自动重复任何不确定操作；保留 checkpoint 及命令日志进行人工检查。完成的阶段可安全跳过。letter 与已完成的 voices/materials 相依，可以在补记失败且撤回处理完成后单独执行。

技术交付不代表人工听音、音色相似度、语义质量或真人认可通过。三项均保留待评。

父任务在原链路之外追加授权了一个不同的文字观点展示样例。仅当 companion 撤回及两方原音拒绝访问、letter 均完成后，可单独运行 `run --stage display --live-ready`。该阶段先核验先前 P01/P04 已保存答案失效、speech 和缓存音频均拒绝，再另建 opinion、明确虚构及只读展示、双方 model-use 都为 false，不挂载或恢复已撤回原音。即使新 companion 回答被模型校验拒绝、未保存答案，仍可在保留该失败的前提下完成旧回答撤回验证和独立展示。此阶段不包含在 `--stage all` 中。

父任务实际锁定后追加授权的 `followup` 阶段只生成原音。它读取 `persona-update-20261012/state.json` 的 calibration/locked_at，并 GET 验证同一待收集录音的锁定答案，记录锁定时间、生成开始及完成时间、音频 SHA 和时长，不上传 Episode。2026-10-12 首次只读检查因 POST 带 UTC 偏移而 SQLite GET 省略偏移失败，尚未调用 TTS；修复按 UTC 时刻比较后，使用独立 `followup_v2` 检查点。v2 拒绝任何已有或不确定的初次 provider 生成操作，保留原 preflight 失败，不重新选择声音结果。
