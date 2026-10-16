# 切换页面时反复显示取消弹窗

2026-10-16，Asia/Singapore。用户在已安装 1.13.2 后反馈打开 App、切换页面时有时反复出现“需要留意／取消”。

## 原因与修改

`RootView` 会把 `AppModel.errorMessage` 作为“需要留意”弹窗正文。花园／单段记忆页及 App 前台生命周期会用 SwiftUI `.task` 执行 `refresh()`；离开页面或生命周期变化会正常取消任务。此前 `refresh()` 把取消也当成服务故障，清空远端展示数据并发布错误。回归实测可复现 `URLError.cancelled`／`NSURLErrorDomain -999`，以及正文“已取消”。旧聊天记忆页的加载也存在相同的取消提示处理。

现在这两个只读加载入口遇到 Task 取消、`CancellationError` 或 `URLError.cancelled` 时正常结束，不发布错误。刷新取消保留已显示内容和已有重要提示；登录失效等真实错误仍沿用现有提示与权限数据清理。没有修改删除、上传、录音或授权操作，也没有隐藏真实网络故障。

## 实际验证

- 修复前3个定向用例：取消请求／取消任务2项失败，登录失效1项通过；失败日志复现弹窗正文被写成“已取消”以及已有内容被清空。测试本体结束后，首次 Xcode 命令在诊断收集阶段未退出，已结束该命令；红灯证据以 `build/cancel-refresh-before-20261016.log` 为准。
- 修复后 `ECSConnectionTests` **39 passed**，含新增4项：取消刷新保留内容且无弹窗、取消任务保留已有提示、离开旧聊天加载不弹取消框、401仍清空权限数据并显示错误。`TwinVoiceCallTests` **23 passed**，合计 **62 passed / 0 failures**，Xcode TEST SUCCEEDED。
- Release 签名构建、`codesign --verify --deep --strict`、`git diff --check` 通过。版本 **1.13.3 / 2026101601** 已覆盖安装到「黑幕」，系统安装清单核对通过；未卸载或清空容器。安装前后9个已有 m4a 文件均存在，大小与修改时间一致。
- 手机再次锁屏，安装后的启动请求被系统拒绝；尚未将本人切页体验记为通过。此前用户解锁后的 1.13.2 启动已确认，但不作为本修复版本的启动证据。

## 证据与范围

逻辑检查结果：`build/cancel-refresh-after-20261016.xcresult`。构建、安装、版本查询与启动分别在 `build/cancel-refresh-release-20261016.log`、`build/cancel-refresh-install-20261016.log`、`build/cancel-refresh-installed-20261016.json`、`build/cancel-refresh-launch-20261016.json`。原音文件清单仅在 ignored `build/private/`，未读取或上传录音内容。

本次只更新 iOS；Backend、Worker、共享 Contract 均未修改或重新发布。此前长静默后第三轮 RTC 超时仍按原发布记录保留，不能把这个弹窗修复当作通话稳定性验收。
