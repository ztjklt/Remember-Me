# iOS 最新源码 GitHub 快照 — 2026-10-16

本人要求将 iOS 最新版上传 GitHub。本快照分支为 `codex/ios-latest-20261016`，源码版本 **1.17.0 / 2026101614**。它包含当前工作区的 iOS 实现，以及[录音豆扫描参数修正](IOS_RECORDING_BEAN_SCAN_2026_10_16.md)。独立 1.16.4 修复包是上次装机版本的最小补丁，不代表本分支的全部功能。

## 内容与运行边界

- iOS App、实时活动扩展、共享属性、设计系统、图片、测试夹具、单元／界面测试、XcodeGen 配置、Swift Package 固定版本和 SDK 准备脚本。
- 相应共享 JSON Schemas、契约检查、授权提案、验证记录及预览。
- Android、Backend、AI Core 的其他工作区源码修改未包含在本次提交。iOS 云端功能继续使用账号所连接的服务；新增采集核对／累计分析能力仍按后端能力声明回退。

厂商 SDK 二进制、构建与签名产物、生成的 UI 测试会话、账号凭据和本人录音未进入 Git。历史验证文档中的 `build/`、本机路径和日志是本地证据索引，不是可从 GitHub 下载的附件。

源码上传不改变线上后端或手机已安装版本，也不代表真实录音豆绑定、长时后台蓝牙或真人声音效果已验收。此前 [1.17.0 采集／花园验证](IOS_ANDROID_CAPTURE_GARDEN_2026_10_16.md) 的结果与限制继续适用。

## 从仓库准备工程

需要 Xcode、XcodeGen 和 Node.js。RTC 使用已固定版本及 SHA256 的官方下载脚本；普通工程保留无录音豆 SDK 时的手机录音回退。

```sh
./apps/ios/scripts/prepare-volcengine.sh
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -configuration Release -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO build
cd packages/contracts
npm ci --ignore-scripts
npm test
```

需要真实录音豆时，使用获许可的 D3200 V1.3.01 本地工具包：

```sh
./apps/ios/scripts/prepare-soundcore.sh '/path/to/iosFrameworkExport-v1.3.01'
```

该脚本生成含录音豆 SDK 的 `project.hardware.yml` 工程；RTC 脚本仍需事先运行。真机安装需配置自己的开发团队及签名。厂商长期密钥只放后端，不写进手机工程。

## 本轮实际检查

暂存文件已导出到独立目录，构建与契约检查从该快照运行：

- 含官方录音豆及 RTC SDK 的 Release 真机目标构建成功；`codesign --verify --deep --strict` 通过。
- 主 App 与录音活动扩展版本均读回 **1.17.0 / 2026101614**。
- 契约依赖按 lock 文件重新安装，`npm test` **72 通过、0 失败、0 跳过**。
- 暂存差异空白检查通过。未重新运行原生单元／界面测试，此前各版本的测试数量不计作本轮新执行结果。

本机证据：`build/ios-github-upload-20261016/` 的 `build-input.json`、`release-build.log`、`contracts-install.log` 和 `contracts-test.log`。本轮不安装手机、不发起录音或通话、不部署服务。
