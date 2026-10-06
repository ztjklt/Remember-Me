# 本机 Agent 调试台

从项目根目录运行 `services/backend/.venv/bin/python scripts/run_agent_demo.py --serve`，在电脑 Chrome 或 Edge 打开 `http://localhost:8000/debug/agent/`。

1. 点击“加载本地会话”，确认页面显示“真实模式”。无需手动复制 token。
2. 展开“添加录音”，点击“选择耳机麦克风”，允许浏览器权限。
3. 开始录音、停止录音，先播放检查声音，再确认录音处理同意和 Cloud Twin 本人单人声明，点击上传。
4. 等待处理完成，依次查看“记忆原文”“当前理解”“提问与回答”“校正与更新”。主页面显示文字；回答依据可展开，历史提取结果、全部 JSON、ID 与会话设置位于底部折叠区。记忆原文显示本次上传的录音，未选择录音时显示最近一段。
5. 输入问题并点击“提问”，回答出现后直接填写校正，点击“保存校正并更新理解”。下方展示你的校正及更新后的理解；再次提问即可验证。

也可选择音频文件或用 Episode ID 继续查看处理。录音最长 5 分钟、上传上限 7 MB；页面关闭会丢弃尚未上传的音频。`--serve --mode fixture` 只验证接线，会明确显示固定测试材料提示。已有服务在运行时直接打开页面，不必重复启动。启动器会在写数据库和日志前检查端口；端口占用时明确报错，运行中任一服务（包括 worker）退出也会显示退出码和日志路径。需要重启时先在原终端 Ctrl-C，确认退出后再启动。

页面只调用现有 Backend API，音频来源使用现有 `IMPORT`；供应商密钥仍只在服务端。凭据不写入浏览器存储，切换会话会清空结果。调试入口只挂载在 demo 启动器，正常 `app.main:app` 不提供演示会话文件。

加载会话会自动读取已有原文与理解。提问调用既有校准接口，一次生成并保存待校正的回答，保证页面显示与提交比较的是同一份答案。提交后保留明确标注的校正前回答，展示本人校正及新理解，五维差异收在调试区。保留 Calibration ID 可在刷新页面后恢复锁定。理解版本变化后需要重新锁定，不能用旧答案校准新模型。可以读取下次问题，或明确撤回 Cloud Twin 同意。

姓名等同音字无法只靠声音确认，转写是机器识别结果。遇到误识别，在本人答案中明确更正；事实纠错更新当前理解，并保留更正依据。问答把完整授权原文、当前理解和本人校正一并交给 LLM；相关校正优先于旧识别，撤回或失效的材料不能使用。历史提取结果保持原样，校准后的 Twin 回答不会拿它覆盖本人的文字更正。

已有错误快照不会因为代码升级自动重写。开发者可使用 `scripts/reapply_agent_calibration.py --calibration-id <已完成的ID> --expected-revision <当前版本>` 预览修正结果；确认后增加 `--apply`。该工具仅使用 configured 演示会话，应用前备份本地数据库，通过既有授权、证据校验和 revision CAS 新增快照，保留原校准记录；有更新校准或 revision 不匹配时拒绝应用。个人报告及备份只保存在忽略的 `build/agent-demo/provider-check/`。

浏览器使用电脑系统的麦克风，因此 Windows Chrome / Edge 可使用 Windows 耳机设备，WSL 服务通过 localhost 提供页面。如果地址无法访问，先检查 demo 启动日志和 WSL localhost 转发。出现麦克风拒绝时，检查浏览器的站点权限和系统麦克风隐私设置，也可以先导入音频定位服务端问题。[浏览器录音需要 localhost 或 HTTPS](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)，此 HTTP 调试地址不直接用于手机局域网录音。

前端静态文件修改后刷新页面；Python 代码或服务端 `.env` 修改后，用 Ctrl-C 停止原 demo 再启动。调试台的固定地址与会话会复用。供应商、原始音频和数据库仍由原有服务管理。

验证：`PYTHONPATH=scripts services/backend/.venv/bin/python -m pytest scripts/agent_console/tests/test_server.py`。前端为无依赖 JavaScript modules，可用 `node --check` 分别检查 `static/capture.js` 和 `static/agent.js`。仓库未为此工具配置独立 lint、format 或 typecheck。

浏览器回归使用独立环境，避免新增服务运行依赖：

```bash
uv venv /tmp/remember-console-venv
uv pip install --python /tmp/remember-console-venv/bin/python playwright
/tmp/remember-console-venv/bin/python -m playwright install chromium
services/backend/.venv/bin/python scripts/run_agent_demo.py --serve --mode fixture --backend-port 8001 --ai-port 8101 --stt-port 8201
```

保持该 fixture 终端运行，在另一个终端按顺序执行：

```bash
/tmp/remember-console-venv/bin/python scripts/agent_console/tests/browser_capture.py
/tmp/remember-console-venv/bin/python scripts/agent_console/tests/browser_agent.py
```

第二个测试依赖第一个创建的 fixture 材料，结束时撤回该测试会话的同意；重新运行时仍按这个顺序。可通过 `REMEMBER_CHROMIUM_PATH` 指定已有 Chromium。这些测试使用模拟麦克风和 fixture 服务，不作为真实语音验收。简化后的真实问答与校正循环见 [QA 验证记录](../../docs/verification/FACTUAL_QA_2026_10_06.md)。真实供应商和浏览器音频传输的实测见 [验证记录](../../docs/verification/BROWSER_AGENT_2026_10_05.md)。
