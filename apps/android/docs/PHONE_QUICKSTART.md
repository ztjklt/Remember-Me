# 电脑 Backend 模式的手机联调

`1.2-local` 默认使用手机独立模式，见 [新版安装与模型设置](LOCAL_AGENT.md)。以下用于旧版或切回电脑模式。

适用于 `1.1-agent`。这是连接 Backend 的安卓客户端；安装 APK 不会把 Python Backend、
数据库、任务 worker 和 AI Core 一起装进手机。编译 APK 与运行服务是两件事。

## 1. 已安装 APK：启动服务，不需要 Gradle

在电脑仓库根目录运行：

```bash
cd /home/qingtian/projects/Remember-Me
services/backend/.venv/bin/python scripts/run_agent_demo.py --serve --mode configured
```

保持终端运行。如果端口已占用，先查看已有服务，不要重复启动或删除数据库。
`configured` 使用已配置的真实供应商；`fixture` 会把录音转成固定测试句，不用于录音验收。

## 2. 截图中的字段怎么填

服务生成并复用 `build/agent-demo/configured/session.json`。在电脑本地打开该文件：

| App 字段 | 填写来源 | 含义 |
| --- | --- | --- |
| Backend 地址 | 下方无线转发完成后填 `http://127.0.0.1:8000` | 自己运行的 Remember Me 服务，不是 DeepSeek/通义地址 |
| Actor Token | `actor_token` 的字符串值 | Backend 签发的会话凭证，不是供应商 API Key |
| Subject ID | `subject_id` 的字符串值 | 当前材料属于哪一个人 |
| RECORDING Consent ID | `recording_consent_id` 的字符串值 | Backend 中有效的录音授权记录 |

复制值时不带 JSON 引号或逗号，三个值必须来自同一个运行实例的会话文件。
需要 Agent 理解与问答时，明确勾选 Cloud Twin 同意和本人单人录音声明。
这些字段是当前原型的联调入口，正常产品应由登录或设备配对自动提供。
会话凭证仅保存在 App 内存，进程退出后需要重新填写；不要把会话文件提交 Git 或公开分享。

## 3. 无线访问当前电脑服务

当前 demo 只监听电脑回环地址。手机上的 `127.0.0.1` 指手机自己，必须先建立转发。
Android 11 及以上可在同一可互访 Wi-Fi 下，开启“开发者选项 → 无线调试”：

1. 点“使用配对码配对设备”，在运行 Backend 的同一 WSL 环境执行 `adb pair 手机IP:配对端口`，按提示输入配对码。
2. 返回无线调试主页面，执行 `adb connect 手机IP:连接端口`。配对端口与连接端口通常不同。
3. 执行 `adb devices` 确认连接。多个设备时，后续命令用 `adb -s 设备序列号 ...`。
4. 执行 `adb reverse tcp:8000 tcp:8000`，手机浏览器访问 `http://127.0.0.1:8000/health`，成功后填 App。

本机 adb 为 `/home/qingtian/projects/Remember-Me/build/android-tools/sdk/platform-tools/adb`，可直接使用完整路径。
换网络、重启或重连后检查转发；只安装 APK、只连同一 Wi-Fi 都不会自动建立转发。
WSL 与手机必须能互访；若配对超时，应检查网络或使用能访问 WSL 服务的 Windows adb 环境。
不要将带有自动读取会话凭证功能的 `/debug/agent/session` 控制台直接开放到公网。
正式远程部署应使用 HTTPS Backend 和正常认证，手机填写部署地址即可。

依据：[Android 无线调试](https://developer.android.com/studio/run/device#connect-to-your-device-using-wi-fi)。

## 4. 开发者重新编译：修复 JAVA_HOME

上一版记录遗漏了 export 命令。本次机器已有 JDK 17 和 SDK 35，在新终端执行完整命令：

```bash
cd /home/qingtian/projects/Remember-Me/apps/android
export JAVA_HOME=/home/qingtian/projects/Remember-Me/build/android-tools/java/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=/home/qingtian/projects/Remember-Me/build/android-tools/sdk
export GRADLE_USER_HOME=/home/qingtian/projects/Remember-Me/build/android-gradle
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$PATH"
./gradlew --no-daemon test assembleDebug assembleDebugAndroidTest lintDebug
```

工具现已恢复到本机持久的忽略目录 `build/android-tools`；以上不是通用安装器。其他机器请安装 JDK 17 和
Android SDK 35 到持久目录，并把对应路径加入自己的 shell 配置。Ubuntu 可通过系统包管理器
安装 `openjdk-17-jdk`；SDK 可用 Android Studio 的 SDK Manager 安装。设置 `JAVA_HOME`
为 JDK 根目录、`ANDROID_HOME` 为 SDK 根目录，不要填 `bin/java` 或 `platform-tools`。
命令行选择 JDK 的规则见 [Android 构建 JDK 文档](https://developer.android.com/build/jdks)。

2026-10-06 用上面完整命令复核；结果见 [验证记录](../../../docs/verification/ANDROID_AGENT_2026_10_06.md)。
原安装包仍可使用；本次文档修正不需要重新安装。
