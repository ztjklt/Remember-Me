# 安装与真实操作：Android 本机联调版

此版本使用真实 Groq ASR 和微信 DeepSeek，APK 不含服务商密钥。当前交付是 **PC 后端 + Android 安装包 / 网页**，不是脱离 PC 的公网成品。Windows 上未编译 iOS，也未声称实体手机已经验证。

## 已配置的开发电脑

在仓库根目录运行（PowerShell）：

```powershell
./tools/Start-RememberMe.ps1 -PythonExe D:/codex_work/remember-me-review/verification-venv/Scripts/python.exe -CheckOnly
./tools/Start-RememberMe.ps1 -PythonExe D:/codex_work/remember-me-review/verification-venv/Scripts/python.exe -AdbExe D:/codex_work/remember-me-toolchain/sdk/platform-tools/adb.exe -Serial emulator-5554 -InstallAndroid
```

脚本会检查现有服务，不重复启动；未启动时先备份 SQLite、执行迁移、启动 API / 处理任务 / 人物任务 / AI Core。测试包不清空已有 App 数据。网页地址 `http://127.0.0.1:8877/workbench/`。本机已经有运行服务时无需重启。

连接实体 Android：开启开发者选项与 USB 调试，USB 连电脑，在手机上确认电脑授权；`adb devices` 找到序列号后替换 `emulator-5554`。安装后使用普通账号，不需要开发身份 Token。录音权限首次弹出时允许；拒绝后可以从系统设置恢复。实体设备操作仍待实际执行。

不要把测试 APK 当作离线模型包：断开 PC 或 ADB 转发后仍可保留本机原音，但云端转写、整理、问答需要重新连通服务。所有人使用同一服务地址时，账号资料按服务端权限隔离。

## 新电脑准备

需要 Python 3.12+、FFmpeg、Android platform-tools（真机/模拟器接入时）和项目源码；首次准备需要网络。

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe -r services/backend/pyproject.toml -r services/ai-core/pyproject.toml
uv pip install --python .venv/Scripts/python.exe "sentence-transformers>=3.0,<6"
```

最后一个依赖用于已有的文字搜索嵌入，不用于语音识别；首次搜索还会下载 `BAAI/bge-small-zh-v1.5` 固定修订的权重。无模型时搜索明确失败，录音/云端整理/完整材料问答仍可运行。本轮已配置环境通过验证；没有把新电脑首次安装冒充实测。

在 `services/backend/.env` 私下配置（文件已忽略，不能填入前端）：

```dotenv
REMEMBER_ENVIRONMENT=development
REMEMBER_ENABLE_WORKBENCH=true
REMEMBER_ALLOW_ACCOUNT_REGISTRATION=true
REMEMBER_DATABASE_URL=sqlite:///./var/remember-me.db
REMEMBER_OBJECT_STORE_BACKEND=local
REMEMBER_OBJECT_STORE_ROOT=./var/object-store
REMEMBER_STT_BACKEND=groq
REMEMBER_GROQ_API_KEY=<服务端专用密钥>
REMEMBER_GROQ_ASR_MODEL=whisper-large-v3
REMEMBER_STT_TIMEOUT_SECONDS=300
REMEMBER_AI_BACKEND=http
REMEMBER_AI_CORE_URL=http://127.0.0.1:8879
REMEMBER_AI_TIMEOUT_SECONDS=90
AI_PROVIDER=weixin
AI_BASE_URL=https://chatapi.weixin.qq.com/openai/v1
AI_MODEL=Deepseek-v4-flash
WEIXIN_CHAT_API_KEY=<服务端专用密钥>
```

若 `services/ai-core/.env` 已存在，它对 AI 设置有覆盖作用，须保持一致。不得覆盖已有数据库路径或使用另一服务商密钥代替。启动：`./tools/Start-RememberMe.ps1 -PythonExe .venv/Scripts/python.exe`。输出中不含密钥。

## 操作顺序

1. 注册账号，进入自己的空白空间；“我的”可保存姓名、方言与含义。
2. “今天”录音，暂停/继续，完成后先播放原音；明确同意云端转写后上传。
3. “档案”核对实际转写，必要时改文字；将用词带入“本次补充说明”或直接输入。确认后才整理。
4. 查看记忆、人物视图、原音。本人书面补充与录音原话分别标注。
5. “对话”提问并核对依据；“我的”生成/审核人物候选。单次经历不自动成为稳定人格。
6. 第二个账号提供读者编号，记录者选择故事授权。分享包括原音、完整核对文字、书面补充和记忆；私人用词表不自动分享。
7. 补充/纠正/变化、待答问题、人物更新须按各自确认流程；退出或撤权后旧内容不能继续读取。

## 要成为任意网络可用的安装包

还需一个持续运行的后端地址及 HTTPS：部署 API、worker、profile-worker、AI Core，共享持久数据库/原音存储与服务端密钥，配置 `REMEMBER_ALLOWED_HOSTS`，在 HTTPS 前置代理后验证账号、上传和权限。当前启动器只监听回环地址，不会公开服务。staging 注册默认关闭，需要运营者明确启用。

Android 构建时用 `-PrememberServiceUrl=https://实际服务域名` 配置根地址，再签署分发包。普通用户不应填写服务商密钥。此过程尚未执行；当前没有已部署公网地址或 iOS 包。上架、备份恢复、账号找回和跨网设备验收另列，不能由本机测试推定完成。
