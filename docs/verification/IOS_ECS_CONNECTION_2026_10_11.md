# iOS 接入现有 ECS 本人空间

日期：2026-10-11。分支 `codex/ios-ecs-integration`，基于 iOS PR #90 的 `cae4fb4`。对照 Android PR #89 的 `ce9382b`；复用其已部署接口，不合并其旧 iOS 文件、不部署服务端代码，不修改共享 Schema。

## 本次交付

- 增加云端连接检查、普通账号登录、本人空间选择、退出与 Keychain 会话保存；保留 Mac 配对入口和上一份 Mac 凭据。
- 默认 ECS 地址及证书指纹复用 Android 内测交付的公开证书；验证指纹、TLS 主机和有效期，不接受现场获取的未知指纹，不跟随重定向。当前证书到期 2027-01-07。
- 登录不自动创建 RECORDING、CLOUD_TWIN 或 VOICE 授权。本人主动上传时复核录音授权；若不存在，才在该操作下创建。云端原音转写按当次 capability 显示用途，并绑定 `metadata.cloud_asr_policy`；转写用途变化时要求重新确认。
- 语音提问另行确认原音用途，通过 `X-Cloud-ASR-Policy` 调用共享转写接口；转写结果仍由用户核对后点击提问。普通记忆录音必须核对文字后才提取。
- 读取原有 Memory、Episode、七领域 Person Model、采集问题和 Twin 接口。云端个人声音生成在此版暂未启用；Mac 声音能力保留。声音读取失败不会挡住基础记忆读取。
- 切换服务前保存当前录音的原 Subject、Actor、服务、证书及 Episode，不自动迁移旧 Mac 数据。不同账号／服务的内容分开显示，返回原连接后可继续查看。刷新、Twin 授权和检索的异步结果在返回时复核原账号／空间，避免回填新账号。
- 补充声音样本试听，提问／样本录音进入后台时停止；普通录音电平去除固定非零下限。
- 云端亲友空间在选择页标明此版尚未接入，不能以 owner 身份读取。故事审核、分享邀请、花田、完整连续聊天仍是后续工作。

## 验证结果

1. 使用 Android 交付证书调用 ECS `/api/v1/service-info` 成功，返回 API `0.7.0`，注册关闭。证书 SAN 对应 `39.108.183.47`。
2. 从实际 iOS `Network.swift` 构建临时 Swift 只读探针，使用已公开的虚构样例账号：固定证书 TLS、登录、空间、capabilities、Memory、Episode、Person Model、问题、consent、calibration 均解码成功。样例返回 10 段录音、61 条记忆、7 个领域；STT 为 paraformer、已配置、存在云端策略，AI 可用。探针仅创建自己的登录会话并在结束后撤销，没有上传音频、提问生成、创建授权或修改样例。
3. iPhone 17 Pro Max / iOS 26.5 模拟器：17 项单元测试、3 项 UI 测试通过，0 失败。新增 6 项覆盖登录／空间解码、语音用途请求头、上传身份及幂等字段、可读错误、旧配对解码、切换服务保存旧 Episode 与账号隔离。
4. 最终连接弹窗调整后，定向复测五入口、云端登录入口、Mac 配对入口，1 项 UI 测试通过。结果包 `build/ios-ecs-connection-ui-final.xcresult`。
   随后补充账号切换后的 Twin 授权／检索回填隔离，17 项单元测试再次通过，0 失败；结果包 `build/ios-ecs-isolation-final.xcresult`。最终签名设备构建通过并更新安装。
5. iPhone 设备目标签名构建成功，`devicectl` 安装并启动成功。设备 iOS 26.6.2；App `me.remember.personal.ios`，显示名 **Remember Me ECS**，版本 `1.1.0`，build `2026101101`。原设备 `me.remember.ios.qa` 未覆盖或卸载，原 App 资料仍在原容器。

命令：

```bash
xcodegen generate --spec apps/ios/project.yml
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS Simulator,id=D2FE37B7-EC92-4C64-A7E0-CEC9F332E987' \
  -derivedDataPath build/ios-ecs-integration-tests \
  -resultBundlePath build/ios-ecs-integration-tests-v2.xcresult \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO COMPILER_INDEX_STORE_ENABLE=NO test
xcodebuild -project apps/ios/RememberMe.xcodeproj -scheme RememberMe \
  -destination 'platform=iOS,id=00008130-000A094C0EE0001C' \
  -derivedDataPath build/ios-ecs-device -allowProvisioningUpdates \
  COMPILER_INDEX_STORE_ENABLE=NO build
```

未把编译、只读样例或安装成功当作真人录音闭环。首次编译发现两个跨文件样式访问错误，修正后测试和签名构建通过。

## 用户在 iPhone 上继续

打开 **Remember Me ECS → Me → 连接服务 → 云端服务**，先检查连接，再登录独立内测账号。单个本人空间自动进入；多个本人空间需要选择。公开样例账号只适合虚构材料，密码不写入 App 或此验证记录。

本人录一段自然讲述并试听，确认本段上传用途，等待机器稿；核对名字、时间、否定后确认整理；再打开 Agents 的问答页，单独同意云端 Twin，问一条材料可以回答的问题并检查原文及原音。记录这条真人旅程后才可声称此版 iPhone 录音闭环通过。

原 QA App、旧 Mac 数据和本机原音不会自动导入新云端空间。新版本无需重新配置 STT 或 LLM 的供应商密钥，服务端保留这些适配器和凭据。未执行数据库迁移、ECS 部署、注册开放或账号创建。

用户需要独立内测账号。当前 Mac 的 SSH 配置没有 Remember Me ECS 别名或对应密钥，SSH agent 无身份；Safari 打开的 ECS 控制台停在阿里云登录页。服务端管理员须在现有后端环境加载 `/etc/remember-me/api.env` 后，使用 `python -m app.account_admin create 用户名 --name 昵称` 交互设定密码；不得重置已有账号或开放公众注册来绕过管理入口。账号和密码不进入版本库或本记录。
