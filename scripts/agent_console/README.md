# 本机 Agent 调试台

从项目根目录运行 `services/backend/.venv/bin/python scripts/run_agent_demo.py --serve`，在电脑 Chrome 或 Edge 打开 `http://localhost:8000/debug/agent/`。

加载本地演示会话，允许麦克风并选择耳机输入，录音、播放检查、确认同意后上传。页面显示异步处理状态、真实 Memory、Person Model 和授权原文。也可选择音频文件或用 Episode ID 继续查看处理。`--serve --mode fixture` 只验证接线，会明确显示固定测试材料提示。

页面只调用现有 Backend API，音频来源使用现有 `IMPORT`；供应商密钥仍只在服务端。凭据不写入浏览器存储，切换会话会清空结果。调试入口只挂载在 demo 启动器，正常 `app.main:app` 不提供演示会话文件。

处理完成后可以问 Twin 并核对原文，点击“先锁定，再校准”后才显示本人答案输入框；提交显示五维差异和新 revision。保留 Calibration ID 可在刷新页面后恢复锁定。理解版本变化后需要重新锁定，不能用旧答案校准新模型。可以读取下次问题，或明确撤回 Cloud Twin 同意。

验证：`PYTHONPATH=scripts services/backend/.venv/bin/python -m pytest scripts/agent_console/tests/test_server.py`。前端为无依赖 JavaScript modules，可用 `node --check scripts/agent_console/static/capture.js` 检查语法。浏览器麦克风需要本机 localhost 或 HTTPS，不能把此 HTTP 调试地址换成手机上的普通局域网地址。

浏览器回归使用独立环境安装 `playwright` 和 Chromium，先启动 `scripts/run_agent_demo.py --serve --mode fixture --backend-port 8001 --ai-port 8101 --stt-port 8201`，再执行 `python scripts/agent_console/tests/browser_capture.py`。可通过 `REMEMBER_CHROMIUM_PATH` 指定已有 Chromium。这个测试使用浏览器模拟麦克风和 fixture 服务，不作为真实语音验收。
